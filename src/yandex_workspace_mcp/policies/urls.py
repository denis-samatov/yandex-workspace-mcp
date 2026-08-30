import ipaddress
import time
import urllib.parse
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

import anyio
import httpx

from ..clients.base import RequestCredentials, RequestSemantics
from ..models.errors import (
    ContractMismatchError,
    InvalidInput,
    PermissionDenied,
    UpstreamTimeout,
    UpstreamUnavailable,
)

_WIKI_ORIGIN = "https://api.wiki.yandex.net"
_DISK_ORIGIN = "https://cloud-api.yandex.net"
_MIN_POLL_INTERVAL = 0.5


class OperationClient(Protocol):
    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response: ...


def _validate_operation_url(value: str, *, origin: str, path_prefix: str) -> str:
    if not isinstance(value, str) or not value:
        raise InvalidInput()
    parsed_input = urllib.parse.urlsplit(value)
    if parsed_input.fragment or parsed_input.username or parsed_input.password:
        raise InvalidInput()
    if parsed_input.scheme or parsed_input.netloc:
        resolved = value
    else:
        if not value.startswith(path_prefix) or value.startswith("//"):
            raise InvalidInput()
        resolved = urllib.parse.urljoin(f"{origin}/", value)
    parsed = urllib.parse.urlsplit(resolved)
    expected = urllib.parse.urlsplit(origin)
    try:
        port = parsed.port
    except ValueError as exc:
        raise InvalidInput() from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname != expected.hostname
        or port not in {None, 443}
        or parsed.fragment
        or parsed.username
        or parsed.password
        or not parsed.path.startswith(path_prefix)
    ):
        raise InvalidInput()
    return resolved


def validate_operation_url(value: str) -> str:
    return _validate_operation_url(value, origin=_WIKI_ORIGIN, path_prefix="/v1/")


def validate_disk_operation_url(value: str) -> str:
    return _validate_operation_url(
        value,
        origin=_DISK_ORIGIN,
        path_prefix="/v1/disk/operations/",
    )


def validate_remote_upload_url(value: str, allowed_hosts: list[str]) -> str:
    if not isinstance(value, str) or not value or not allowed_hosts:
        raise PermissionDenied()
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise PermissionDenied() from exc
    host = (parsed.hostname or "").casefold().rstrip(".")
    normalized_allowed = {
        item.casefold().rstrip(".")
        for item in allowed_hosts
        if isinstance(item, str) and item and "*" not in item and ":" not in item
    }
    try:
        ipaddress.ip_address(host)
        literal = True
    except ValueError:
        literal = False
    if (
        parsed.scheme != "https"
        or not host
        or host not in normalized_allowed
        or literal
        or host == "localhost"
        or host.endswith(".localhost")
        or port not in {None, 443}
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise PermissionDenied()
    return value


def normalize_public_url(value: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise PermissionDenied() from exc
    host = (parsed.hostname or "").casefold().rstrip(".")
    if (
        parsed.scheme.casefold() != "https"
        or not host
        or port not in {None, 443}
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise PermissionDenied()
    path = parsed.path.rstrip("/") or "/"
    return urllib.parse.urlunsplit(("https", host, path, parsed.query, ""))


def authorize_public_locator(
    *,
    public_key: str | None,
    public_url: str | None,
    allowed_values: list[str],
) -> tuple[str | None, str | None]:
    if (public_key is None) == (public_url is None) or not allowed_values:
        raise PermissionDenied()
    normalized_allowed: set[str] = set()
    for value in allowed_values:
        if value.startswith("https://"):
            normalized_allowed.add(normalize_public_url(value))
        else:
            normalized_allowed.add(value)
    if public_key is not None:
        if public_key not in normalized_allowed:
            raise PermissionDenied()
        return public_key, None
    assert public_url is not None
    normalized_url = normalize_public_url(public_url)
    if normalized_url not in normalized_allowed:
        raise PermissionDenied()
    return None, normalized_url


async def poll_operation(
    client: OperationClient,
    status_url: str,
    *,
    credentials: RequestCredentials | None = None,
    interval: float = _MIN_POLL_INTERVAL,
    timeout: float = 30.0,
    max_polls: int = 100,
    sleeper: Callable[[float], Awaitable[None]] = anyio.sleep,
    clock: Callable[[], float] = time.monotonic,
    validator: Callable[[str], str] = validate_operation_url,
) -> dict[str, object]:
    url = validator(status_url)
    delay = max(_MIN_POLL_INTERVAL, interval)
    started_at = clock()
    for poll_number in range(max_polls):
        if clock() - started_at >= timeout:
            raise UpstreamTimeout()
        response = await client._request(
            "GET",
            url,
            semantics=RequestSemantics.SAFE_READ,
            credentials=credentials,
            operation_timeout=max(0.1, timeout - (clock() - started_at)),
        )
        if 300 <= response.status_code < 400:
            raise InvalidInput()
        try:
            payload = response.json()
        except (ValueError, TypeError) as exc:
            raise ContractMismatchError() from exc
        if not isinstance(payload, dict):
            raise ContractMismatchError()
        status = payload.get("status")
        if status == "success":
            return payload
        if status == "failed":
            raise UpstreamUnavailable()
        if status not in {"scheduled", "in_progress"}:
            raise ContractMismatchError()
        if poll_number == max_polls - 1:
            break
        if clock() - started_at + delay >= timeout:
            raise UpstreamTimeout()
        await sleeper(delay)
    raise UpstreamTimeout()

import ipaddress
from collections.abc import Sequence
from typing import Any

from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from ..auth.oauth import registration_source_var


class RegistrationSourceMiddleware:
    """Bind dynamic registration accounting to the direct network peer."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    @property
    def router(self) -> Any:
        return self.app.router  # type: ignore[attr-defined]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        client = scope.get("client")
        source = client[0] if scope["type"] == "http" and client else "unknown"
        token = registration_source_var.set(source)
        try:
            await self.app(scope, receive, send)
        finally:
            registration_source_var.reset(token)


class TrustedProxyHeadersMiddleware:
    """Honor proxy scheme/host only when the direct peer is explicitly trusted."""

    def __init__(self, app: ASGIApp, trusted_cidrs: Sequence[str]) -> None:
        self.app = app
        self._networks = tuple(ipaddress.ip_network(value, strict=False) for value in trusted_cidrs)

    @property
    def router(self) -> Any:
        return self.app.router  # type: ignore[attr-defined]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self._trusted(scope):
            await self.app(scope, receive, send)
            return
        headers = list(scope.get("headers", []))
        forwarded_proto = self._single_header(headers, b"x-forwarded-proto")
        forwarded_host = self._single_header(headers, b"x-forwarded-host")
        if forwarded_proto is False or forwarded_host is False:
            await PlainTextResponse("Invalid forwarded headers", status_code=400)(
                scope, receive, send
            )
            return
        updated = dict(scope)
        if isinstance(forwarded_proto, str):
            if forwarded_proto not in {"http", "https"}:
                await PlainTextResponse("Invalid forwarded scheme", status_code=400)(
                    scope, receive, send
                )
                return
            updated["scheme"] = forwarded_proto
        if isinstance(forwarded_host, str):
            if not forwarded_host or any(char in forwarded_host for char in "\r\n/@"):
                await PlainTextResponse("Invalid forwarded host", status_code=400)(
                    scope, receive, send
                )
                return
            headers = [(name, value) for name, value in headers if name.lower() != b"host"]
            headers.append((b"host", forwarded_host.encode("ascii", errors="strict")))
            updated["headers"] = headers
        await self.app(updated, receive, send)

    def _trusted(self, scope: Scope) -> bool:
        client = scope.get("client")
        if not client:
            return False
        try:
            address = ipaddress.ip_address(client[0])
        except ValueError:
            return False
        return any(address in network for network in self._networks)

    @staticmethod
    def _single_header(headers: list[tuple[bytes, bytes]], name: bytes) -> str | bool | None:
        values = [value for key, value in headers if key.lower() == name]
        if not values:
            return None
        if len(values) != 1:
            return False
        try:
            decoded = values[0].decode("ascii").strip().lower()
        except UnicodeDecodeError:
            return False
        if not decoded or "," in decoded:
            return False
        return decoded

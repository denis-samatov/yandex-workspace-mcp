import asyncio
import importlib

import httpx
import pytest

from yandex_workspace_mcp.models.errors import UpstreamTimeout, UpstreamUnavailable


def test_request_semantics_exist() -> None:
    base = importlib.import_module("yandex_workspace_mcp.clients.base")
    assert hasattr(base, "RequestSemantics")
    assert hasattr(base, "RequestCredentials")


def _client(
    handler: httpx.AsyncBaseTransport,
    *,
    sleeps: list[float] | None = None,
    clock: "FakeClock | None" = None,
):
    base = importlib.import_module("yandex_workspace_mcp.clients.base")
    sleep_values = sleeps if sleeps is not None else []

    async def sleeper(delay: float) -> None:
        sleep_values.append(delay)
        if clock:
            clock.value += delay

    return base.BaseYandexClient(
        base_url="https://api.example.test",
        client=httpx.AsyncClient(
            base_url="https://api.example.test",
            transport=handler,
        ),
        sleeper=sleeper,
        jitter=lambda _low, high: high,
        clock=clock or __import__("time").monotonic,
    )


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


@pytest.mark.asyncio
async def test_logical_read_post_retries_retryable_statuses() -> None:
    base = importlib.import_module("yandex_workspace_mcp.clients.base")
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503 if attempts < 3 else 200, request=request)

    client = _client(httpx.MockTransport(handler))
    response = await client._request(
        "POST", "/search", semantics=base.RequestSemantics.LOGICAL_READ
    )

    assert response.status_code == 200
    assert attempts == 3
    await client.close()


@pytest.mark.asyncio
async def test_safe_read_clamps_retry_after() -> None:
    base = importlib.import_module("yandex_workspace_mcp.clients.base")
    sleeps: list[float] = []
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"Retry-After": "99"}, request=request)
        return httpx.Response(200, request=request)

    client = _client(httpx.MockTransport(handler), sleeps=sleeps)
    await client._request("GET", "/resources", semantics=base.RequestSemantics.SAFE_READ)

    assert attempts == 2
    assert sleeps == [3.0]
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "semantics",
    ["MUTATION", "SIGNED_UPLOAD"],
)
async def test_unsafe_operations_never_replay_5xx(semantics: str) -> None:
    base = importlib.import_module("yandex_workspace_mcp.clients.base")
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, text="secret upstream body", request=request)

    client = _client(httpx.MockTransport(handler))
    with pytest.raises(UpstreamUnavailable) as caught:
        await client._request("POST", "/write", semantics=getattr(base.RequestSemantics, semantics))

    assert attempts == 1
    assert "secret upstream body" not in str(caught.value)
    await client.close()


@pytest.mark.asyncio
async def test_mutation_never_replays_connect_error() -> None:
    base = importlib.import_module("yandex_workspace_mcp.clients.base")
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("network secret", request=request)

    client = _client(httpx.MockTransport(handler))
    with pytest.raises(UpstreamUnavailable):
        await client._request("DELETE", "/resource", semantics=base.RequestSemantics.MUTATION)

    assert attempts == 1
    await client.close()


@pytest.mark.asyncio
async def test_safe_timeout_retries_then_normalizes() -> None:
    base = importlib.import_module("yandex_workspace_mcp.clients.base")
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("timeout secret", request=request)

    client = _client(httpx.MockTransport(handler))
    with pytest.raises(UpstreamTimeout) as caught:
        await client._request("GET", "/resource", semantics=base.RequestSemantics.SAFE_READ)

    assert attempts == 3
    assert "timeout secret" not in str(caught.value)
    await client.close()


@pytest.mark.asyncio
async def test_overall_deadline_stops_before_a_fourth_attempt() -> None:
    base = importlib.import_module("yandex_workspace_mcp.clients.base")
    clock = FakeClock()
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, request=request)

    client = _client(httpx.MockTransport(handler), clock=clock)
    with pytest.raises(UpstreamTimeout):
        await client._request(
            "GET",
            "/resource",
            semantics=base.RequestSemantics.SAFE_READ,
            operation_timeout=0.75,
        )

    assert attempts == 2
    assert clock.value == 0.5
    await client.close()


@pytest.mark.asyncio
async def test_request_credentials_are_isolated_per_concurrent_call() -> None:
    base = importlib.import_module("yandex_workspace_mcp.clients.base")
    observed: dict[str, str | None] = {}
    both_started = asyncio.Event()
    started = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal started
        started += 1
        if started == 2:
            both_started.set()
        await both_started.wait()
        observed[request.url.path] = request.headers.get("Authorization")
        return httpx.Response(200, request=request)

    client = _client(httpx.MockTransport(handler))
    await asyncio.gather(
        client._request(
            "GET",
            "/one",
            semantics=base.RequestSemantics.SAFE_READ,
            credentials=base.RequestCredentials(token="token-one"),
        ),
        client._request(
            "GET",
            "/two",
            semantics=base.RequestSemantics.SAFE_READ,
            credentials=base.RequestCredentials(token="token-two", headers={"X-Org-Id": "org-two"}),
        ),
    )

    assert observed == {"/one": "OAuth token-one", "/two": "OAuth token-two"}
    assert "Authorization" not in client.client.headers
    await client.close()

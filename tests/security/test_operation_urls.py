import asyncio

import httpx
import pytest

from yandex_workspace_mcp.models.errors import InvalidInput, UpstreamTimeout
from yandex_workspace_mcp.policies.urls import poll_operation, validate_operation_url


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            "/v1/operations/clone/task",
            "https://api.wiki.yandex.net/v1/operations/clone/task",
        ),
        (
            "https://api.wiki.yandex.net/v1/operations/clone/task?cursor=x",
            "https://api.wiki.yandex.net/v1/operations/clone/task?cursor=x",
        ),
        (
            "https://api.wiki.yandex.net:443/v1/operations/clone/task",
            "https://api.wiki.yandex.net:443/v1/operations/clone/task",
        ),
    ],
)
def test_operation_url_accepts_relative_or_exact_origin_https(value: str, expected: str) -> None:
    assert validate_operation_url(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "http://api.wiki.yandex.net/v1/operations/x",
        "https://evil.example/v1/operations/x",
        "https://api.wiki.yandex.net.evil.example/v1/operations/x",
        "https://user:pass@api.wiki.yandex.net/v1/operations/x",
        "https://api.wiki.yandex.net:444/v1/operations/x",
        "https://api.wiki.yandex.net/v1/operations/x#fragment",
        "//evil.example/v1/operations/x",
        "/other/status",
    ],
)
def test_operation_url_rejects_unsafe_targets(value: str) -> None:
    with pytest.raises(InvalidInput):
        validate_operation_url(value)


class _FakeClient:
    def __init__(self, bodies: list[dict[str, object]], status: int = 200) -> None:
        self.bodies = iter(bodies)
        self.status = status
        self.urls: list[str] = []

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        self.urls.append(path)
        return httpx.Response(self.status, json=next(self.bodies))


@pytest.mark.asyncio
async def test_poller_obeys_minimum_interval_and_stops_on_success() -> None:
    client = _FakeClient(
        [
            {"status": "scheduled"},
            {"status": "in_progress"},
            {"status": "success", "result": {"page": {"id": 7, "slug": "Team/Copy"}}},
        ]
    )
    delays: list[float] = []

    async def sleeper(delay: float) -> None:
        delays.append(delay)

    result = await poll_operation(
        client,
        "/v1/operations/clone/task",
        interval=0.1,
        sleeper=sleeper,
        clock=lambda: 0.0,
    )

    assert result["status"] == "success"
    assert delays == [0.5, 0.5]
    assert len(client.urls) == 3


@pytest.mark.asyncio
async def test_poller_has_poll_cap_and_propagates_cancellation() -> None:
    client = _FakeClient([{"status": "scheduled"}, {"status": "scheduled"}])

    async def no_sleep(delay: float) -> None:
        return None

    with pytest.raises(UpstreamTimeout):
        await poll_operation(
            client,
            "/v1/operations/clone/task",
            max_polls=2,
            sleeper=no_sleep,
            clock=lambda: 0.0,
        )

    async def cancelled(delay: float) -> None:
        raise asyncio.CancelledError

    cancelling = _FakeClient([{"status": "scheduled"}])
    with pytest.raises(asyncio.CancelledError):
        await poll_operation(
            cancelling,
            "/v1/operations/clone/task",
            sleeper=cancelled,
            clock=lambda: 0.0,
        )

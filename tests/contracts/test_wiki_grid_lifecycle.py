from unittest.mock import AsyncMock

import httpx
import pytest

from yandex_workspace_mcp.clients.wiki import YandexWikiClient
from yandex_workspace_mcp.models.errors import InvalidInput, RevisionConflict
from yandex_workspace_mcp.models.wiki import (
    GridCopyInput,
    GridCreateInput,
    GridDeleteInput,
    GridSort,
    GridUpdateInput,
    PageLocator,
    WikiGrid,
    WikiGridPage,
    WikiPage,
)
from yandex_workspace_mcp.services.wiki import WikiService


def _grid_payload(*, grid_id: str = "grid-1", revision: str = "1") -> dict[str, object]:
    return {
        "id": grid_id,
        "title": "Roadmap",
        "page": {"id": 42, "slug": "Team/Page"},
        "revision": revision,
        "structure": {
            "columns": [{"id": "c1", "slug": "name", "type": "string"}],
            "default_sort": [{"slug": "name", "direction": "asc"}],
        },
        "rows": [],
    }


def _client(handler) -> YandexWikiClient:
    return YandexWikiClient(
        client=httpx.AsyncClient(
            base_url="https://api.wiki.yandex.net/v1",
            transport=httpx.MockTransport(handler),
        )
    )


@pytest.mark.asyncio
async def test_create_and_update_grid_use_exact_wire_contracts() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST" and request.url.path.endswith("/grid-1"):
            return httpx.Response(200, json={"revision": "8", "future": "ignored"})
        return httpx.Response(
            200,
            json=_grid_payload(revision="8" if request.method == "GET" else "1"),
        )

    client = _client(handler)
    created = await client.create_grid(
        42,
        GridCreateInput(locator=PageLocator(page_id=42), title="Roadmap"),
    )
    updated = await client.update_grid(
        GridUpdateInput(
            grid_id="grid-1",
            revision=7,
            title="Roadmap",
            default_sort=[GridSort(column_slug="name", direction="asc")],
        )
    )

    assert created.id == "grid-1"
    assert updated.grid.revision == "8"
    assert [(request.method, request.url.path) for request in requests] == [
        ("POST", "/v1/grids"),
        ("POST", "/v1/grids/grid-1"),
        ("GET", "/v1/grids/grid-1"),
    ]
    assert requests[0].read() == b'{"title":"Roadmap","page":{"id":42}}'
    assert requests[1].read() == (b'{"revision":7,"title":"Roadmap","default_sort":{"name":"asc"}}')
    assert dict(requests[2].url.params) == {"revision": "8", "fields": "attributes"}
    await client.close()


@pytest.mark.asyncio
async def test_copy_validates_operation_url_and_delete_maps_204() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "operation": {"type": "clone", "id": "copy-1"},
                    "status_url": "/v1/operations/clone/copy-1",
                    "dry_run": False,
                    "future": "ignored",
                },
            )
        return httpx.Response(204)

    client = _client(handler)
    copied = await client.copy_grid(
        "grid-1",
        destination_slug="Team/Destination",
        title="Copy",
    )
    deleted = await client.delete_grid(GridDeleteInput(grid_id="grid-1", revision=8))

    assert copied.model_dump() == {
        "status": "pending",
        "operation_id": "copy-1",
        "grid": None,
        "warnings": [],
    }
    assert deleted.model_dump() == {"grid_id": "grid-1", "deleted": True}
    assert [(request.method, request.url.path) for request in requests] == [
        ("POST", "/v1/grids/grid-1/clone"),
        ("DELETE", "/v1/grids/grid-1"),
    ]
    assert requests[0].read() == (b'{"target":"Team/Destination","with_data":false,"title":"Copy"}')
    assert requests[1].content == b""
    await client.close()


@pytest.mark.asyncio
async def test_copy_rejects_untrusted_operation_url() -> None:
    client = _client(
        lambda request: httpx.Response(
            200,
            json={
                "operation": {"type": "clone", "id": "copy-1"},
                "status_url": "https://evil.example/status",
            },
        )
    )
    with pytest.raises(InvalidInput):
        await client.copy_grid("grid-1", destination_slug="Team/Destination")
    await client.close()


@pytest.mark.asyncio
async def test_conflict_and_transport_failure_do_not_replay_grid_mutations() -> None:
    calls = 0

    def conflict(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(409, json={"error_code": "CONFLICT"})

    client = _client(conflict)
    with pytest.raises(RevisionConflict):
        await client.update_grid(GridUpdateInput(grid_id="grid-1", revision=7, title="New"))
    assert calls == 1
    await client.close()


@pytest.mark.asyncio
async def test_service_authorizes_grid_owner_and_copy_destination_before_mutation() -> None:
    client = AsyncMock()
    client.get_grid.return_value = WikiGrid(id="grid-1", page=WikiGridPage(id=42, slug="Team/Page"))
    client.get_page.side_effect = [
        WikiPage(id=42, slug="Team/Page"),
        WikiPage(id=84, slug="Team/Destination"),
    ]
    client.copy_grid.return_value = __import__(
        "yandex_workspace_mcp.models.wiki", fromlist=["GridOperationResponse"]
    ).GridOperationResponse(status="pending", operation_id="copy-1")
    service = WikiService(client, ["/Team"], True, True, True)

    result = await service.copy_grid(
        GridCopyInput(
            grid_id="grid-1",
            destination=PageLocator(page_id=84),
            title="Copy",
        )
    )

    assert result.operation_id == "copy-1"
    client.copy_grid.assert_awaited_once_with(
        "grid-1",
        destination_slug="Team/Destination",
        title="Copy",
        credentials=None,
    )


@pytest.mark.asyncio
async def test_service_resolves_owner_before_update_and_delete() -> None:
    client = AsyncMock()
    client.get_grid.return_value = WikiGrid(id="grid-1", page=WikiGridPage(id=42, slug="Team/Page"))
    client.get_page.return_value = WikiPage(id=42, slug="Team/Page")
    client.update_grid.return_value = __import__(
        "yandex_workspace_mcp.models.wiki", fromlist=["GridUpdateResponse"]
    ).GridUpdateResponse(grid=client.get_grid.return_value)
    client.delete_grid.return_value = __import__(
        "yandex_workspace_mcp.models.wiki", fromlist=["GridDeleteResponse"]
    ).GridDeleteResponse(grid_id="grid-1")
    service = WikiService(client, ["/Team"], True, True, True)

    await service.update_grid(GridUpdateInput(grid_id="grid-1", revision=7, title="New"))
    await service.delete_grid(GridDeleteInput(grid_id="grid-1"))

    assert client.get_grid.await_count == 2
    assert client.get_page.await_count == 2
    client.update_grid.assert_awaited_once()
    client.delete_grid.assert_awaited_once()

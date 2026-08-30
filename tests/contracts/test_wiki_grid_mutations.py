import asyncio

import httpx
import pytest

from yandex_workspace_mcp.clients.wiki import YandexWikiClient
from yandex_workspace_mcp.models.errors import RevisionConflict
from yandex_workspace_mcp.models.wiki import (
    GridCellsUpdateInput,
    GridCellUpdate,
    GridColumnCreate,
    GridColumnMoveInput,
    GridColumnsAddInput,
    GridColumnsDeleteInput,
    GridRowMoveInput,
    GridRowsAddInput,
    GridRowsDeleteInput,
    WikiGrid,
    WikiGridPage,
    WikiPage,
)
from yandex_workspace_mcp.services.wiki import WikiService


def _client(handler) -> YandexWikiClient:
    return YandexWikiClient(
        client=httpx.AsyncClient(
            base_url="https://api.wiki.yandex.net/v1",
            transport=httpx.MockTransport(handler),
        )
    )


@pytest.mark.asyncio
async def test_all_seven_grid_mutations_use_exact_endpoints_and_payloads() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/cells"):
            return httpx.Response(
                200,
                json={
                    "revision": "9",
                    "cells": [{"row_id": "r1", "column_slug": "name", "value": "Beta"}],
                    "future": "ignored",
                },
            )
        if request.method == "POST" and request.url.path.endswith("/rows"):
            return httpx.Response(
                200,
                json={
                    "revision": "8",
                    "results": [{"id": "r2", "row": ["Alpha"]}],
                },
            )
        return httpx.Response(200, json={"revision": "10", "future": "ignored"})

    client = _client(handler)
    added_rows = await client.add_grid_rows(
        GridRowsAddInput(
            grid_id="g",
            revision=7,
            rows=[{"name": "Alpha"}],
            after_row_id="r1",
        )
    )
    updated_cells = await client.update_grid_cells(
        GridCellsUpdateInput(
            grid_id="g",
            revision=8,
            cells=[
                GridCellUpdate(row_id="r1", column_slug="name", value="Beta"),
                GridCellUpdate(row_id="r1", column_id="c2", value=None),
            ],
        )
    )
    await client.delete_grid_rows(GridRowsDeleteInput(grid_id="g", revision=9, row_ids=["r2"]))
    await client.move_grid_row(GridRowMoveInput(grid_id="g", revision=10, row_id="r1", position=0))
    await client.add_grid_columns(
        GridColumnsAddInput(
            grid_id="g",
            revision=11,
            position=1,
            columns=[
                GridColumnCreate(
                    title="Owner",
                    slug="owner",
                    type="staff",
                    required=False,
                ),
                GridColumnCreate(
                    title="State",
                    slug="state",
                    type="select",
                    required=True,
                    select_options=["Open", "Done"],
                ),
            ],
        )
    )
    await client.delete_grid_columns(
        GridColumnsDeleteInput(grid_id="g", revision=12, column_slugs=["state"])
    )
    await client.move_grid_column(
        GridColumnMoveInput(grid_id="g", revision=13, column_slug="owner", position=0)
    )

    assert added_rows.revision == "8"
    assert added_rows.results[0].id == "r2"
    assert updated_cells.model_dump() == {
        "revision": "9",
        "cells": [
            {
                "row_id": "r1",
                "column_id": None,
                "column_slug": "name",
                "value": "Beta",
            }
        ],
        "warnings": [],
    }
    assert [(request.method, request.url.path) for request in requests] == [
        ("POST", "/v1/grids/g/rows"),
        ("POST", "/v1/grids/g/cells"),
        ("DELETE", "/v1/grids/g/rows"),
        ("POST", "/v1/grids/g/rows/move"),
        ("POST", "/v1/grids/g/columns"),
        ("DELETE", "/v1/grids/g/columns"),
        ("POST", "/v1/grids/g/columns/move"),
    ]
    assert [request.read() for request in requests] == [
        b'{"revision":7,"rows":[{"name":"Alpha"}],"after_row_id":"r1"}',
        (
            b'{"revision":8,"cells":[{"row_id":"r1","column_slug":"name",'
            b'"value":"Beta"},{"row_id":"r1","column_id":"c2","value":null}]}'
        ),
        b'{"revision":9,"row_ids":["r2"]}',
        b'{"revision":10,"row_id":"r1","position":0}',
        (
            b'{"revision":11,"columns":[{"title":"Owner","slug":"owner",'
            b'"type":"staff","required":false,"multiple":false},{"title":"State",'
            b'"slug":"state","type":"select","required":true,"select_options":['
            b'"Open","Done"]}],"position":1}'
        ),
        b'{"revision":12,"column_slugs":["state"]}',
        b'{"revision":13,"column_slug":"owner","position":0}',
    ]
    await client.close()


@pytest.mark.asyncio
async def test_grid_mutation_conflict_is_not_replayed() -> None:
    calls = 0

    def conflict(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(409, json={"error_code": "CONFLICT"})

    client = _client(conflict)
    with pytest.raises(RevisionConflict):
        await client.delete_grid_rows(GridRowsDeleteInput(grid_id="g", revision=9, row_ids=["r2"]))
    assert calls == 1
    await client.close()


@pytest.mark.asyncio
async def test_service_serializes_mutations_for_the_same_grid() -> None:
    active = 0
    max_active = 0

    class Client:
        async def get_grid(self, grid_input, *, credentials=None):
            return WikiGrid(id="g", page=WikiGridPage(id=42, slug="Team/Page"))

        async def get_page(self, locator, *, credentials=None):
            return WikiPage(id=42, slug="Team/Page")

        async def move_grid_row(self, grid_input, *, credentials=None):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0)
            active -= 1
            return __import__(
                "yandex_workspace_mcp.models.wiki", fromlist=["GridMutationResponse"]
            ).GridMutationResponse(revision="11")

    service = WikiService(Client(), ["/Team"], True, True, True)  # type: ignore[arg-type]
    await asyncio.gather(
        service.move_grid_row(GridRowMoveInput(grid_id="g", revision=10, row_id="r1", position=0)),
        service.move_grid_row(GridRowMoveInput(grid_id="g", revision=11, row_id="r2", position=1)),
    )

    assert max_active == 1


@pytest.mark.asyncio
async def test_delete_scope_does_not_require_write_permission() -> None:
    class Client:
        async def get_grid(self, grid_input, *, credentials=None):
            return WikiGrid(id="g", page=WikiGridPage(id=42, slug="Team/Page"))

        async def get_page(self, locator, *, credentials=None):
            return WikiPage(id=42, slug="Team/Page")

        async def delete_grid_rows(self, grid_input, *, credentials=None):
            return __import__(
                "yandex_workspace_mcp.models.wiki", fromlist=["GridMutationResponse"]
            ).GridMutationResponse(revision="11")

    service = WikiService(Client(), ["/Team"], True, False, True)  # type: ignore[arg-type]
    result = await service.delete_grid_rows(
        GridRowsDeleteInput(grid_id="g", revision=10, row_ids=["r1"])
    )

    assert result.revision == "11"

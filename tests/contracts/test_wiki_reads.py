import json

import httpx
import pytest

from yandex_workspace_mcp.clients.wiki import YandexWikiClient
from yandex_workspace_mcp.models.errors import ContractMismatchError
from yandex_workspace_mcp.models.wiki import (
    GridGetInput,
    PageListInput,
    PageLocator,
    PageResourceListInput,
)


def _client(handler) -> YandexWikiClient:
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(
        base_url="https://api.wiki.yandex.net/v1",
        transport=transport,
    )
    return YandexWikiClient(client=http)


@pytest.mark.asyncio
async def test_get_page_by_slug_and_id_uses_official_fields() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": 42,
                "slug": "team/page",
                "title": "Page",
                "content": "Body",
                "attributes": {
                    "created_at": "2026-01-01T00:00:00Z",
                    "keywords": ["wire-only"],
                },
                "future": "ignored",
            },
        )

    client = _client(handler)
    by_slug = await client.get_page(PageLocator(slug="team/page"))
    by_id = await client.get_page(PageLocator(page_id=42))

    assert [(request.url.path, dict(request.url.params)) for request in requests] == [
        ("/v1/pages", {"slug": "team/page", "fields": "content,attributes"}),
        ("/v1/pages/42", {"fields": "content,attributes"}),
    ]
    assert by_slug == by_id
    assert by_slug.created_at == "2026-01-01T00:00:00Z"
    assert "keywords" not in by_slug.attributes
    await client.close()


@pytest.mark.asyncio
async def test_descendant_id_and_slug_paths_and_paging() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": [{"id": 2, "slug": "team/child"}]})

    client = _client(handler)
    models = __import__("yandex_workspace_mcp.models.wiki", fromlist=["DescendantsInput"])
    await client.get_descendants(
        models.DescendantsInput(
            locator=PageLocator(slug="team"), include_self=True, page_size=75, cursor="next"
        )
    )
    await client.get_descendants(
        models.DescendantsInput(locator=PageLocator(page_id=1), page_size=25)
    )

    assert [(request.url.path, dict(request.url.params)) for request in requests] == [
        (
            "/v1/pages/descendants",
            {"slug": "team", "include_self": "true", "page_size": "75", "cursor": "next"},
        ),
        ("/v1/pages/1/descendants", {"include_self": "false", "page_size": "25"}),
    ]
    await client.close()


@pytest.mark.asyncio
async def test_page_collection_reads_use_exact_endpoints_and_query_names() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path
        if path.endswith("/comments"):
            body = {"results": [{"id": 1, "body": "ok", "new": True}], "future": True}
        elif path.endswith("/resources"):
            body = {
                "results": [{"type": "grid", "item": {"id": "g", "title": "Grid", "new": True}}]
            }
        elif path.endswith("/attachments"):
            body = {
                "results": [
                    {
                        "id": 3,
                        "name": "a.txt",
                        "mimetype": "text/plain",
                        "size": "12",
                        "download_url": "https://secret.example/token",
                    }
                ]
            }
        else:
            body = {"results": [{"id": "g", "title": "Grid"}]}
        return httpx.Response(200, json=body)

    client = _client(handler)
    common = PageListInput(locator=PageLocator(page_id=42), page_size=20, cursor="cursor")
    comments = await client.get_comments(common)
    resources = await client.get_resources(
        PageResourceListInput(
            locator=PageLocator(page_id=42),
            resource_types=["attachment", "grid"],
            page_size=20,
            cursor="cursor",
        )
    )
    attachments = await client.get_attachments(common)
    grids = await client.get_grids(common)

    assert [(request.url.path, dict(request.url.params)) for request in requests] == [
        ("/v1/pages/42/comments", {"page_size": "20", "cursor": "cursor"}),
        (
            "/v1/pages/42/resources",
            {"page_size": "20", "cursor": "cursor", "types": "attachment,grid"},
        ),
        ("/v1/pages/42/attachments", {"page_size": "20", "cursor": "cursor"}),
        ("/v1/pages/42/grids", {"page_size": "20", "cursor": "cursor"}),
    ]
    assert comments.results[0].body == "ok"
    assert resources.results[0].type == "grid"
    assert attachments.results[0].mime_type == "text/plain"
    assert attachments.results[0].size == 12
    assert "download_url" not in attachments.results[0].model_dump()
    assert grids.results[0].id == "g"
    await client.close()


@pytest.mark.asyncio
async def test_get_grid_maps_official_structure_and_row_shape() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "id": "grid-1",
                "title": "Roadmap",
                "page": {"id": 42, "slug": "team"},
                "revision": "7",
                "structure": {
                    "columns": [{"id": "c1", "slug": "name", "title": "Name", "type": "string"}],
                    "default_sort": [{"slug": "name", "direction": "asc"}],
                },
                "rows": [{"id": "r1", "row": ["Alpha"]}],
                "future": {"ignored": True},
            },
        )

    client = _client(handler)
    grid = await client.get_grid(
        GridGetInput(grid_id="grid-1", revision=7, row_ids=["r1"], column_slugs=["name"])
    )

    assert captured[0].url.path == "/v1/grids/grid-1"
    assert dict(captured[0].url.params) == {
        "revision": "7",
        "only_rows": "r1",
        "only_cols": "name",
        "fields": "attributes",
    }
    assert grid.rows[0].cells == {"name": "Alpha"}
    assert grid.default_sort[0].column_slug == "name"
    await client.close()


@pytest.mark.asyncio
async def test_empty_collection_bodies_are_empty_but_entity_body_must_be_valid() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/attachments"):
            return httpx.Response(204)
        return httpx.Response(200, content=b"")

    client = _client(handler)
    empty = await client.get_attachments(PageListInput(locator=PageLocator(page_id=1)))
    assert empty.results == []
    with pytest.raises(ContractMismatchError):
        await client.get_page(PageLocator(page_id=1))
    await client.close()


@pytest.mark.asyncio
async def test_malformed_successful_grid_payload_is_contract_mismatch() -> None:
    client = _client(
        lambda request: httpx.Response(200, content=json.dumps({"title": "missing id"}))
    )
    with pytest.raises(ContractMismatchError):
        await client.get_grid(GridGetInput(grid_id="g"))
    await client.close()

import importlib

import httpx
import pytest


@pytest.mark.asyncio
async def test_descendants_uses_exact_pagination_query() -> None:
    wiki_client = importlib.import_module("yandex_workspace_mcp.clients.wiki")
    wiki_models = importlib.import_module("yandex_workspace_mcp.models.wiki")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "results": [{"id": 1, "slug": "Team/Page", "new": True}],
                "next_cursor": "next",
            },
            request=request,
        )

    client = wiki_client.YandexWikiClient(
        token="token",
        client=httpx.AsyncClient(
            base_url="https://api.wiki.yandex.net/v1",
            transport=httpx.MockTransport(handler),
        ),
    )
    result = await client.get_descendants(
        wiki_models.DescendantsInput(
            locator=wiki_models.PageLocator(slug="Team"),
            page_size=100,
            cursor="cursor",
        )
    )

    assert requests[0].url.path == "/v1/pages/descendants"
    assert dict(requests[0].url.params) == {
        "slug": "Team",
        "include_self": "false",
        "page_size": "100",
        "cursor": "cursor",
    }
    assert result.results[0].slug == "Team/Page"
    assert result.next_cursor == "next"
    await client.close()


@pytest.mark.asyncio
async def test_get_page_parses_typed_public_page() -> None:
    wiki_client = importlib.import_module("yandex_workspace_mcp.clients.wiki")
    wiki_models = importlib.import_module("yandex_workspace_mcp.models.wiki")

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"id": 4, "slug": "Team/Page", "title": "Page", "content": "Body"},
            request=request,
        )

    client = wiki_client.YandexWikiClient(
        token="token",
        client=httpx.AsyncClient(
            base_url="https://api.wiki.yandex.net/v1",
            transport=httpx.MockTransport(handler),
        ),
    )
    page = await client.get_page(wiki_models.PageLocator(slug="Team/Page"))

    assert page.id == 4
    assert page.content == "Body"
    await client.close()

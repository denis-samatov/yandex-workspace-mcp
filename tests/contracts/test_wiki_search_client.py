import importlib

import httpx
import pytest


def _wiki_client(handler: httpx.AsyncBaseTransport):
    module = importlib.import_module("yandex_workspace_mcp.clients.wiki")
    return module.YandexWikiClient(
        token="token",
        org_id="org",
        client=httpx.AsyncClient(
            base_url="https://api.wiki.yandex.net/v1",
            transport=handler,
        ),
    )


def test_wiki_search_client_method_exists() -> None:
    module = importlib.import_module("yandex_workspace_mcp.clients.wiki")
    assert hasattr(module.YandexWikiClient, "search")


@pytest.mark.asyncio
async def test_search_posts_exact_body_and_maps_wire_extras() -> None:
    wiki_models = importlib.import_module("yandex_workspace_mcp.models.wiki")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": 1,
                        "slug": "Team/Page",
                        "title": "Page",
                        "content": "excerpt",
                        "type": "page",
                        "new": "ignored",
                    }
                ],
                "new_envelope": True,
            },
            request=request,
        )

    client = _wiki_client(httpx.MockTransport(handler))
    result = await client.search(wiki_models.WikiSearchInput(query="needle", limit=20))

    assert requests[0].method == "POST"
    assert requests[0].url.path == "/v1/search"
    assert requests[0].read() == b'{"query":"needle","limit":20}'
    assert requests[0].headers["Authorization"] == "OAuth token"
    assert requests[0].headers["X-Org-Id"] == "org"
    assert result.results[0].content_excerpt == "excerpt"
    assert "new" not in result.model_dump_json()
    await client.close()


@pytest.mark.asyncio
async def test_search_cluster_filter_and_legacy_page_slice() -> None:
    wiki_models = importlib.import_module("yandex_workspace_mcp.models.wiki")
    bodies: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(__import__("json").loads(request.read()))
        return httpx.Response(
            200,
            json={
                "results": [
                    {"id": index, "slug": f"Team/{index}", "type": "page"} for index in range(30)
                ]
            },
            request=request,
        )

    client = _wiki_client(httpx.MockTransport(handler))
    result = await client.search(
        wiki_models.WikiSearchInput(query="q", limit=10, page=3), cluster="Team"
    )

    assert bodies == [{"query": "q", "limit": 30, "filters": {"cluster": "Team"}}]
    assert [item.id for item in result.results] == list(range(20, 30))
    await client.close()


@pytest.mark.asyncio
async def test_search_page_above_five_does_not_call_upstream() -> None:
    wiki_models = importlib.import_module("yandex_workspace_mcp.models.wiki")
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(500, request=request)

    client = _wiki_client(httpx.MockTransport(handler))
    result = await client.search(wiki_models.WikiSearchInput(query="q", page=6))

    assert attempts == 0
    assert result.results == []
    assert result.pagination_exhausted is True
    await client.close()


@pytest.mark.asyncio
async def test_search_classifies_filter_drift_and_contract_mismatch() -> None:
    wiki_client = importlib.import_module("yandex_workspace_mcp.clients.wiki")
    wiki_models = importlib.import_module("yandex_workspace_mcp.models.wiki")
    responses = [
        (400, {"code": "UNKNOWN_FIELD", "message": "filters is unknown"}),
        (200, {"results": "not-a-list"}),
    ]

    async def handler(request: httpx.Request) -> httpx.Response:
        status, payload = responses.pop(0)
        return httpx.Response(status, json=payload, request=request)

    client = _wiki_client(httpx.MockTransport(handler))
    with pytest.raises(wiki_client.SearchFilterUnsupported):
        await client.search(wiki_models.WikiSearchInput(query="q"), cluster="Team")
    with pytest.raises(wiki_client.ContractMismatchError):
        await client.search(wiki_models.WikiSearchInput(query="q"))
    await client.close()

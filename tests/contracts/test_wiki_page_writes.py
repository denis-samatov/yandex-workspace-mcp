from unittest.mock import AsyncMock

import httpx
import pytest

from yandex_workspace_mcp.clients.wiki import YandexWikiClient
from yandex_workspace_mcp.models.errors import PermissionDenied, RevisionConflict
from yandex_workspace_mcp.models.wiki import (
    CommentCreateInput,
    PageAppendInput,
    PageCloneInput,
    PageCreateInput,
    PageLocator,
    PageUpdateInput,
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
async def test_page_create_update_append_and_comment_exact_wire_contracts() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/comments"):
            return httpx.Response(200, json={"id": 5, "body": "hello"})
        return httpx.Response(
            200,
            json={"id": 42, "slug": "Team/Page", "title": "Title", "content": "Body"},
        )

    client = _client(handler)
    locator = PageLocator(page_id=42)
    await client.create_page(PageCreateInput(slug="Team/Page", title="Title", content="Body"))
    await client.update_page(
        42,
        PageUpdateInput(locator=locator, content="New", allow_merge=False, is_silent=False),
    )
    await client.append_page(42, PageAppendInput(locator=locator, content="More", location="top"))
    await client.append_page(
        42, PageAppendInput(locator=locator, content="Under", anchor="section")
    )
    await client.add_comment(
        42,
        CommentCreateInput(locator=locator, body="hello", parent_comment_id="4"),
    )

    assert [(request.method, request.url.path) for request in requests] == [
        ("POST", "/v1/pages"),
        ("POST", "/v1/pages/42"),
        ("POST", "/v1/pages/42/append-content"),
        ("POST", "/v1/pages/42/append-content"),
        ("POST", "/v1/pages/42/comments"),
    ]
    assert dict(requests[0].url.params) == {"fields": "content,attributes"}
    assert requests[0].read() == b'{"slug":"Team/Page","title":"Title","content":"Body"}'
    assert dict(requests[1].url.params) == {
        "allow_merge": "false",
        "is_silent": "false",
        "fields": "content,attributes",
    }
    assert requests[1].read() == b'{"content":"New"}'
    assert requests[2].read() == b'{"content":"More","body":{"location":"top"}}'
    assert requests[3].read() == b'{"content":"Under","anchor":{"name":"section"}}'
    assert requests[4].read() == b'{"body":"hello","parent_id":"4"}'
    await client.close()


@pytest.mark.asyncio
async def test_clone_posts_once_and_polls_validated_operation(monkeypatch) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "operation": {"type": "clone", "id": "task"},
                    "status_url": "/v1/operations/clone/task",
                },
            )
        return httpx.Response(
            200,
            json={"status": "success", "result": {"page": {"id": 8, "slug": "Team/Copy"}}},
        )

    client = _client(handler)
    result = await client.clone_page(
        42,
        PageCloneInput(source=PageLocator(page_id=42), destination_slug="Team/Copy", title="Copy"),
    )

    assert result.model_dump() == {"id": 8, "slug": "Team/Copy", "status": "completed"}
    assert [(request.method, request.url.path) for request in requests] == [
        ("POST", "/v1/pages/42/clone"),
        ("GET", "/v1/operations/clone/task"),
    ]
    assert requests[0].read() == b'{"target":"Team/Copy","subscribe_me":false,"title":"Copy"}'
    await client.close()


@pytest.mark.asyncio
async def test_conflict_and_transport_failure_never_replay_mutation() -> None:
    calls = 0

    def conflict(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(409, json={"error_code": "CONFLICT"})

    client = _client(conflict)
    with pytest.raises(RevisionConflict):
        await client.update_page(
            42,
            PageUpdateInput(locator=PageLocator(page_id=42), content="New"),
        )
    assert calls == 1
    await client.close()


@pytest.mark.asyncio
async def test_services_authorize_source_and_destination_before_clone() -> None:
    client = AsyncMock()
    client.get_page.return_value = __import__(
        "yandex_workspace_mcp.models.wiki", fromlist=["WikiPage"]
    ).WikiPage(id=42, slug="Team/Page")
    client.clone_page.return_value = __import__(
        "yandex_workspace_mcp.models.wiki", fromlist=["PageCloneResponse"]
    ).PageCloneResponse(id=8, slug="Team/Copy")
    service = WikiService(client, ["/Team"], True, True, True)

    result = await service.clone_page(
        PageCloneInput(source=PageLocator(page_id=42), destination_slug="Team/Copy")
    )
    assert result.id == 8
    client.clone_page.assert_awaited_once()

    with pytest.raises(PermissionDenied):
        await service.clone_page(
            PageCloneInput(source=PageLocator(page_id=42), destination_slug="Other/Copy")
        )
    assert client.clone_page.await_count == 1

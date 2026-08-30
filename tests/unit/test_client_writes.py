"""HTTP-level regression tests for representative client write methods."""

import httpx
import pytest
import respx

from yandex_workspace_mcp.clients.disk import YandexDiskClient
from yandex_workspace_mcp.clients.wiki import YandexWikiClient
from yandex_workspace_mcp.models.errors import PermissionDenied, RevisionConflict
from yandex_workspace_mcp.models.wiki import PageCreateInput, PageLocator, PageUpdateInput


@pytest.fixture
def disk_client():
    return YandexDiskClient(token="test-token")


@pytest.fixture
def wiki_client():
    return YandexWikiClient(token="test-token")


@pytest.mark.asyncio
@respx.mock
async def test_disk_create_folder(disk_client):
    route = respx.put("https://cloud-api.yandex.net/v1/disk/resources").mock(
        return_value=httpx.Response(201)
    )
    await disk_client.create_folder("/Work/new-folder")
    assert route.called
    assert route.calls.last.request.url.params["path"] == "/Work/new-folder"


@pytest.mark.asyncio
@respx.mock
async def test_disk_copy(disk_client):
    route = respx.post("https://cloud-api.yandex.net/v1/disk/resources/copy").mock(
        return_value=httpx.Response(201)
    )
    await disk_client.copy_resource("/Work/a.txt", "/Work/b.txt")
    assert route.called
    params = route.calls.last.request.url.params
    assert params["from"] == "/Work/a.txt"
    assert params["path"] == "/Work/b.txt"


@pytest.mark.asyncio
@respx.mock
async def test_disk_move(disk_client):
    route = respx.post("https://cloud-api.yandex.net/v1/disk/resources/move").mock(
        return_value=httpx.Response(201)
    )
    await disk_client.move_resource("/Work/a.txt", "/Work/b.txt")
    assert route.called


@pytest.mark.asyncio
@respx.mock
async def test_disk_delete(disk_client):
    route = respx.delete("https://cloud-api.yandex.net/v1/disk/resources").mock(
        return_value=httpx.Response(204)
    )
    await disk_client.delete_resource("/Work/a.txt", permanently=True)
    assert route.called
    assert route.calls.last.request.url.params["permanently"] == "true"


@pytest.mark.asyncio
@respx.mock
async def test_disk_write_raises_on_error_status(disk_client):
    respx.put("https://cloud-api.yandex.net/v1/disk/resources").mock(
        return_value=httpx.Response(409, json={"message": "already exists"})
    )
    with pytest.raises(RevisionConflict):
        await disk_client.create_folder("/Work/existing")


@pytest.mark.asyncio
@respx.mock
async def test_wiki_create_page(wiki_client):
    route = respx.post("https://api.wiki.yandex.net/v1/pages").mock(
        return_value=httpx.Response(200, json={"id": 42, "slug": "test", "title": "Test"})
    )
    result = await wiki_client.create_page(
        PageCreateInput(slug="test", title="Test", content="body")
    )
    assert route.called
    assert result.id == 42


@pytest.mark.asyncio
@respx.mock
async def test_wiki_update_page(wiki_client):
    route = respx.post("https://api.wiki.yandex.net/v1/pages/42").mock(
        return_value=httpx.Response(200, json={"id": 42, "content": "updated"})
    )
    result = await wiki_client.update_page(
        42,
        PageUpdateInput(locator=PageLocator(page_id=42), content="updated"),
    )
    assert route.called
    assert route.calls.last.request.url.path == "/v1/pages/42"
    assert result.content == "updated"


@pytest.mark.asyncio
@respx.mock
async def test_wiki_write_raises_on_error_status(wiki_client):
    respx.post("https://api.wiki.yandex.net/v1/pages").mock(
        return_value=httpx.Response(403, json={"message": "forbidden"})
    )
    with pytest.raises(PermissionDenied):
        await wiki_client.create_page(PageCreateInput(slug="x", title="x", content="x"))

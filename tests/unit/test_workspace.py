from unittest.mock import AsyncMock

import pytest

from yandex_workspace_mcp.services.disk import DiskService
from yandex_workspace_mcp.services.wiki import WikiService
from yandex_workspace_mcp.services.workspace import WorkspaceService


@pytest.fixture
def disk_service():
    client = AsyncMock()
    return DiskService(client=client, allowed_roots=["/"], can_read=True, can_write=True, can_delete=True)

@pytest.fixture
def wiki_service():
    client = AsyncMock()
    return WikiService(client=client, allowed_roots=["/"], can_read=True, can_write=True, can_delete=True)

@pytest.mark.asyncio
async def test_workspace_search(disk_service, wiki_service):
    wiki_service.client.search.return_value = {
        "results": [{"slug": "test", "title": "Test Page", "url": "https://wiki.yandex.ru/test"}]
    }
    disk_service.client.search.return_value = {
        "items": [{"name": "test.txt", "path": "/test.txt", "file": "https://downloader..."}]
    }
    
    svc = WorkspaceService(disk=disk_service, wiki=wiki_service)
    res = await svc.search("test")
    
    assert len(res.results) == 2
    assert res.results[0].id == "wiki:page:test"
    assert res.results[0].source == "wiki"
    assert res.results[1].id == "disk:path:/test.txt"
    assert res.results[1].source == "disk"

@pytest.mark.asyncio
async def test_workspace_fetch_wiki(disk_service, wiki_service):
    wiki_service.client.get_page.return_value = {
        "title": "Test Page",
        "content": "Hello World",
        "url": "https://wiki.yandex.ru/test",
        "revision": {"id": 123}
    }
    
    svc = WorkspaceService(disk=disk_service, wiki=wiki_service)
    res = await svc.fetch("wiki:page:test")
    
    assert res.title == "Test Page"
    assert res.text == "Hello World"
    assert res.metadata["source"] == "wiki"

@pytest.mark.asyncio
async def test_workspace_fetch_disk(disk_service, wiki_service):
    disk_service.client.get_metadata.return_value = {
        "name": "test.txt",
        "mime_type": "text/plain",
        "file": "https://downloader.yandex.net/...",
        "size": 10
    }
    disk_service.client.read_file_text.return_value = "File content"
    
    svc = WorkspaceService(disk=disk_service, wiki=wiki_service)
    res = await svc.fetch("disk:path:/test.txt")
    
    assert res.title == "test.txt"
    assert res.text == "File content"
    assert res.metadata["mime_type"] == "text/plain"
    
@pytest.mark.asyncio
async def test_workspace_fetch_unknown():
    svc = WorkspaceService(disk=None, wiki=None)
    with pytest.raises(ValueError, match="Unknown resource ID format"):
        await svc.fetch("unknown:id:test")

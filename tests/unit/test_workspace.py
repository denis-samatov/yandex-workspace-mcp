from unittest.mock import AsyncMock

import pytest

from yandex_workspace_mcp.models.disk import DiskResource, DiskResourcePage, DiskSearchResponse
from yandex_workspace_mcp.models.errors import UpstreamUnavailable
from yandex_workspace_mcp.models.wiki import WikiPage, WikiSearchItem, WikiSearchResponse
from yandex_workspace_mcp.policies.cursors import CursorCodec
from yandex_workspace_mcp.services.disk import DiskService
from yandex_workspace_mcp.services.wiki import WikiService
from yandex_workspace_mcp.services.workspace import WorkspaceService


@pytest.fixture
def disk_service():
    client = AsyncMock()
    signed = AsyncMock()
    signed.download.return_value = b"File content"
    return DiskService(
        client=client,
        allowed_roots=["/"],
        can_read=True,
        can_write=True,
        can_delete=True,
        signed_client=signed,
    )


@pytest.fixture
def wiki_service():
    client = AsyncMock()
    return WikiService(
        client=client, allowed_roots=["/", "test"], can_read=True, can_write=True, can_delete=True
    )


@pytest.mark.asyncio
async def test_workspace_search(disk_service, wiki_service):
    wiki_service.client.search.return_value = WikiSearchResponse(
        results=[WikiSearchItem(id=1, slug="test", title="Test Page", type="page")]
    )
    disk_service.client.list_files.return_value = DiskResourcePage(
        items=[DiskResource(name="test.txt", path="/test.txt", type="file")],
        limit=20,
        offset=0,
    )

    svc = WorkspaceService(disk=disk_service, wiki=wiki_service)
    res = await svc.search("test")

    assert len(res.results) == 2
    assert res.results[0].id == "wiki:page:test"
    assert res.results[0].source == "wiki"
    assert res.results[1].id == "disk:path:/test.txt"
    assert res.results[1].source == "disk"


@pytest.mark.asyncio
async def test_workspace_search_round_robins_wiki_first() -> None:
    wiki = AsyncMock()
    wiki.can_read = True
    wiki.allowed_roots = ["/Team"]
    wiki.search.return_value = WikiSearchResponse(
        results=[
            WikiSearchItem(id=1, slug="Team/W1", title="W1", type="page"),
            WikiSearchItem(id=2, slug="Team/W2", title="W2", type="page"),
        ]
    )
    disk = AsyncMock()
    disk.can_read = True
    disk.allowed_roots = ["/Work"]
    disk.search.return_value = DiskSearchResponse(
        query="q",
        items=[
            DiskResource(path="/Work/D1", name="D1", type="file"),
            DiskResource(path="/Work/D2", name="D2", type="file"),
        ],
    )
    service = WorkspaceService(
        disk=disk,
        wiki=wiki,
        cursor_codec=CursorCodec((b"w" * 32,)),
    )

    result = await service.search("q", limit=4, principal="person")

    assert [item.title for item in result.results] == ["W1", "D1", "W2", "D2"]
    assert result.sources["wiki"].state == "success"
    assert result.sources["disk"].state == "success"


@pytest.mark.asyncio
async def test_workspace_search_reports_partial_failure() -> None:
    wiki = AsyncMock()
    wiki.can_read = True
    wiki.allowed_roots = ["/Team"]
    wiki.search.side_effect = UpstreamUnavailable()
    disk = AsyncMock()
    disk.can_read = True
    disk.allowed_roots = ["/Work"]
    disk.search.return_value = DiskSearchResponse(
        query="q",
        items=[DiskResource(path="/Work/D1", name="D1", type="file")],
    )
    service = WorkspaceService(disk=disk, wiki=wiki)

    result = await service.search("q")

    assert [item.title for item in result.results] == ["D1"]
    assert result.partial_failures == {"wiki": "upstream_unavailable"}
    assert result.sources["wiki"].state == "failure"


@pytest.mark.asyncio
async def test_workspace_search_raises_when_all_sources_fail() -> None:
    wiki = AsyncMock()
    wiki.can_read = True
    wiki.allowed_roots = ["/Team"]
    wiki.search.side_effect = UpstreamUnavailable()
    disk = AsyncMock()
    disk.can_read = True
    disk.allowed_roots = ["/Work"]
    disk.search.side_effect = UpstreamUnavailable()

    with pytest.raises(UpstreamUnavailable):
        await WorkspaceService(disk=disk, wiki=wiki).search("q")


@pytest.mark.asyncio
async def test_workspace_cursor_embeds_disk_offset_and_binds_principal() -> None:
    codec = CursorCodec((b"w" * 32,))
    disk_codec = CursorCodec((b"d" * 32,))
    wiki = AsyncMock()
    wiki.can_read = True
    wiki.allowed_roots = ["/Team"]
    wiki.search.return_value = WikiSearchResponse(
        results=[WikiSearchItem(id=1, slug="Team/W1", title="W1", type="page")]
    )
    disk = AsyncMock()
    disk.can_read = True
    disk.allowed_roots = ["/Work"]
    disk.cursor_codec = disk_codec
    disk_state = __import__(
        "yandex_workspace_mcp.policies.cursors", fromlist=["DiskSearchCursorV1"]
    ).DiskSearchCursorV1(
        query_hash=disk_codec.query_hash("q"),
        principal_hash=disk_codec.principal_hash("person"),
        offset=50,
    )
    disk.search.return_value = DiskSearchResponse(
        query="q",
        items=[DiskResource(path="/Work/D1", name="D1", type="file")],
        next_cursor=disk_codec.encode_disk(disk_state),
    )
    service = WorkspaceService(disk=disk, wiki=wiki, cursor_codec=codec)

    first = await service.search("q", limit=2, principal="person")

    assert first.next_cursor is not None
    decoded = codec.decode_workspace(
        first.next_cursor,
        query="q",
        principal="person",
        enabled_sources={"wiki", "disk"},
        allowed_roots={"/Team"},
    )
    assert decoded.sources.disk is not None
    assert decoded.sources.disk.offset == 50
    assert disk_state.model_dump_json() not in first.next_cursor

    with pytest.raises(ValueError, match="cursor"):
        await service.search("q", cursor=first.next_cursor, principal="other")


@pytest.mark.asyncio
async def test_workspace_fetch_wiki(disk_service, wiki_service):
    wiki_service.client.get_page.return_value = WikiPage(
        id=1,
        slug="test",
        title="Test Page",
        content="Hello World",
        url="https://wiki.yandex.ru/test",
    )

    svc = WorkspaceService(disk=disk_service, wiki=wiki_service)
    res = await svc.fetch("wiki:page:test")

    assert res.title == "Test Page"
    assert res.text == "Hello World"
    assert res.metadata["source"] == "wiki"


@pytest.mark.asyncio
async def test_workspace_fetch_disk(disk_service, wiki_service):
    disk_service.client.get_metadata.return_value = DiskResource(
        name="test.txt",
        path="/test.txt",
        type="file",
        mime_type="text/plain",
        size=10,
    )
    from yandex_workspace_mcp.models.disk import DiskLinkResponse

    disk_service.client.get_download_link.return_value = DiskLinkResponse(
        download_url="https://downloader.disk.yandex.net/file"
    )

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

"""Regression tests for service-layer audit logging on representative operations."""

from unittest.mock import AsyncMock, patch

import pytest

from yandex_workspace_mcp.models.disk import DiskLinkResponse, DiskResource
from yandex_workspace_mcp.models.wiki import WikiPage
from yandex_workspace_mcp.services.disk import DiskService
from yandex_workspace_mcp.services.wiki import WikiService


def make_disk_service():
    return DiskService(
        client=AsyncMock(),
        allowed_roots=["/"],
        can_read=True,
        can_write=True,
        can_delete=True,
        signed_client=AsyncMock(),
    )


def make_wiki_service():
    return WikiService(
        client=AsyncMock(), allowed_roots=["/"], can_read=True, can_write=True, can_delete=True
    )


@pytest.mark.asyncio
async def test_disk_upload_is_audit_logged():
    svc = make_disk_service()
    with patch("yandex_workspace_mcp.services.disk.audit_logger") as mock_logger:
        await svc.upload("/Work/note.txt", "content")
        mock_logger.log.assert_called_once()
        assert mock_logger.log.call_args.args[0] == "disk.upload"
        assert mock_logger.log.call_args.kwargs["path"] == "/Work/note.txt"


@pytest.mark.asyncio
async def test_disk_delete_is_audit_logged():
    svc = make_disk_service()
    with patch("yandex_workspace_mcp.services.disk.audit_logger") as mock_logger:
        await svc.delete("/Work/note.txt", permanently=True)
        mock_logger.log.assert_called_once()
        assert mock_logger.log.call_args.args[0] == "disk.delete"


@pytest.mark.asyncio
async def test_disk_create_folder_is_audit_logged():
    svc = make_disk_service()
    with patch("yandex_workspace_mcp.services.disk.audit_logger") as mock_logger:
        await svc.create_folder("/Work/new")
        mock_logger.log.assert_called_once_with(
            "disk.create_folder", path="/Work/new", result="success"
        )


@pytest.mark.asyncio
async def test_disk_move_is_audit_logged():
    svc = make_disk_service()
    with patch("yandex_workspace_mcp.services.disk.audit_logger") as mock_logger:
        await svc.move("/Work/a.txt", "/Work/b.txt")
        mock_logger.log.assert_called_once_with(
            "disk.move",
            from_path="/Work/a.txt",
            to_path="/Work/b.txt",
            result="success",
        )


@pytest.mark.asyncio
async def test_disk_read_is_not_audit_logged():
    """Read-only operations aren't destructive/write actions and shouldn't be audit-logged."""
    svc = make_disk_service()
    svc.client.get_metadata.return_value = DiskResource(
        path="/Work/note.txt",
        name="note.txt",
        type="file",
        mime_type="text/plain",
    )
    svc.client.get_download_link.return_value = DiskLinkResponse(
        download_url="https://downloader.disk.yandex.net/file"
    )
    svc.signed_client.download.return_value = b"content"
    with patch("yandex_workspace_mcp.services.disk.audit_logger") as mock_logger:
        await svc.read_file("/Work/note.txt")
        mock_logger.log.assert_not_called()


@pytest.mark.asyncio
async def test_wiki_create_page_is_audit_logged():
    svc = make_wiki_service()
    with patch("yandex_workspace_mcp.services.wiki.audit_logger") as mock_logger:
        await svc.create_page("projects/x", "Title", "body")
        mock_logger.log.assert_called_once_with(
            "wiki.create_page", slug="projects/x", result="success"
        )


@pytest.mark.asyncio
async def test_wiki_update_page_is_audit_logged():
    svc = make_wiki_service()
    svc.client.get_page.return_value = WikiPage(id=42, slug="projects/x")
    with patch("yandex_workspace_mcp.services.wiki.audit_logger") as mock_logger:
        await svc.update_page("projects/x", "new body")
        mock_logger.log.assert_called_once_with(
            "wiki.update_page", slug="projects/x", result="success"
        )

"""Service-layer permission-gating tests.

policies/paths.py has its own tests for path validation, but nothing
previously exercised the read_only / can_write / can_delete gates that the
services actually enforce before a write or delete reaches the client.
"""

from unittest.mock import AsyncMock

import pytest

from yandex_workspace_mcp.models.errors import InvalidPath, PermissionDenied
from yandex_workspace_mcp.services.disk import DiskService
from yandex_workspace_mcp.services.wiki import WikiService


def make_disk_service(*, can_read=True, can_write=True, can_delete=True, allowed_roots=None):
    return DiskService(
        client=AsyncMock(),
        allowed_roots=allowed_roots or ["/"],
        can_read=can_read,
        can_write=can_write,
        can_delete=can_delete,
    )


def make_wiki_service(*, can_read=True, can_write=True, can_delete=True, allowed_roots=None):
    return WikiService(
        client=AsyncMock(),
        allowed_roots=allowed_roots or ["/"],
        can_read=can_read,
        can_write=can_write,
        can_delete=can_delete,
    )


@pytest.mark.asyncio
async def test_disk_upload_rejected_in_read_only_mode():
    svc = make_disk_service(can_write=False)
    with pytest.raises(PermissionDenied):
        await svc.upload("/Work/note.txt", "content")
    svc.client.upload_file_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_disk_create_folder_rejected_in_read_only_mode():
    svc = make_disk_service(can_write=False)
    with pytest.raises(PermissionDenied):
        await svc.create_folder("/Work/new")
    svc.client.create_folder.assert_not_awaited()


@pytest.mark.asyncio
async def test_disk_delete_rejected_without_delete_permission():
    svc = make_disk_service(can_write=True, can_delete=False)
    with pytest.raises(PermissionDenied):
        await svc.delete("/Work/note.txt")
    svc.client.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_disk_read_rejected_when_read_disabled():
    svc = make_disk_service(can_read=False)
    with pytest.raises(PermissionDenied):
        await svc.read_file("/Work/note.txt")
    svc.client.get_metadata.assert_not_awaited()


@pytest.mark.asyncio
async def test_disk_write_rejected_for_out_of_tree_path():
    svc = make_disk_service(can_write=True, allowed_roots=["/Work"])
    with pytest.raises(InvalidPath):
        await svc.upload("/Personal/secret.txt", "content")
    svc.client.upload_file_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_wiki_create_page_rejected_in_read_only_mode():
    svc = make_wiki_service(can_write=False)
    with pytest.raises(PermissionDenied):
        await svc.create_page("projects/x", "Title", "body")
    svc.client.create_page.assert_not_awaited()


@pytest.mark.asyncio
async def test_wiki_update_page_rejected_in_read_only_mode():
    svc = make_wiki_service(can_write=False)
    with pytest.raises(PermissionDenied):
        await svc.update_page("projects/x", "new body")
    svc.client.get_page.assert_not_awaited()
    svc.client.update_page.assert_not_awaited()


@pytest.mark.asyncio
async def test_wiki_write_rejected_for_out_of_tree_slug():
    svc = make_wiki_service(can_write=True, allowed_roots=["projects"])
    with pytest.raises(InvalidPath):
        await svc.create_page("personal/diary", "Title", "body")
    svc.client.create_page.assert_not_awaited()

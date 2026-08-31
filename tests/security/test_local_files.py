import os
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from yandex_workspace_mcp.models.disk import DiskOperationResponse
from yandex_workspace_mcp.models.errors import InvalidPath
from yandex_workspace_mcp.policies.local_files import open_allowed_local_file
from yandex_workspace_mcp.services.disk import DiskService


def test_empty_allowlist_and_outside_file_fail_closed(tmp_path: Path) -> None:
    source = tmp_path / "file.txt"
    source.write_text("data", encoding="utf-8")
    with pytest.raises(InvalidPath):
        open_allowed_local_file(str(source), [], max_bytes=100)

    allowed = tmp_path / "allowed"
    allowed.mkdir()
    with pytest.raises(InvalidPath):
        open_allowed_local_file(str(source), [str(allowed)], max_bytes=100)


def test_descriptor_opener_rejects_parent_and_final_symlinks(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("secret", encoding="utf-8")
    (allowed / "parent-link").symlink_to(outside, target_is_directory=True)
    (allowed / "file-link").symlink_to(secret)

    for candidate in (allowed / "parent-link" / "secret.txt", allowed / "file-link"):
        with pytest.raises(InvalidPath):
            open_allowed_local_file(str(candidate), [str(allowed)], max_bytes=100)


@pytest.mark.skipif(
    os.name != "posix",
    reason="open_allowed_local_file() intentionally refuses all local access on non-POSIX systems",
)
def test_regular_size_and_descriptor_identity_are_checked(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    source = allowed / "file.txt"
    source.write_bytes(b"hello")

    with open_allowed_local_file(str(source), [str(allowed)], max_bytes=5) as opened:
        assert opened.basename == "file.txt"
        assert opened.size == 5
        assert opened.read(5) == b"hello"
        opened.verify_identity()

    with pytest.raises(InvalidPath):
        open_allowed_local_file(str(source), [str(allowed)], max_bytes=4)
    with pytest.raises(InvalidPath):
        open_allowed_local_file(str(allowed), [str(allowed)], max_bytes=100)


@pytest.mark.parametrize("suffix", ["\x00bad", "bad\\name", "bad\u212a.txt", "bad\x01.txt"])
def test_ambiguous_local_paths_are_rejected(tmp_path: Path, suffix: str) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    with pytest.raises(InvalidPath):
        open_allowed_local_file(str(allowed / suffix), [str(allowed)], max_bytes=100)


@pytest.mark.skipif(os.name != "posix", reason="descriptor walk is POSIX-specific")
def test_open_handle_remains_usable_without_reopening_path(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    source = allowed / "file.txt"
    source.write_bytes(b"original")
    opened = open_allowed_local_file(str(source), [str(allowed)], max_bytes=100)
    moved = allowed / "moved.txt"
    source.rename(moved)
    try:
        assert opened.read() == b"original"
    finally:
        opened.close()


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.name != "posix",
    reason="open_allowed_local_file() intentionally refuses all local access on non-POSIX systems",
)
async def test_disk_local_upload_owns_and_closes_authorized_descriptor(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    source = allowed / "payload.bin"
    source.write_bytes(b"payload")
    client = AsyncMock()
    client.upload_local_file.return_value = DiskOperationResponse(
        status="completed", path="/Work/payload.bin"
    )
    service = DiskService(
        client,
        ["/Work"],
        True,
        True,
        False,
        upload_allowed_dirs=[str(allowed)],
        max_upload_bytes=100,
        signed_client=AsyncMock(),
    )

    result = await service.upload_local_file(str(source), "/Work/payload.bin")

    assert result.path == "/Work/payload.bin"
    opened = client.upload_local_file.await_args.args[1]
    with pytest.raises(InvalidPath):
        opened.verify_identity()

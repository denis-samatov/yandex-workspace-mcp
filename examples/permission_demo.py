"""Credential-free service-layer demo. All upstream operations are mocked."""

import asyncio
from unittest.mock import AsyncMock

from yandex_workspace_mcp.models.errors import InvalidPath, PermissionDenied
from yandex_workspace_mcp.services.disk import DiskService


async def main() -> None:
    client = AsyncMock()
    read_only = DiskService(
        client=client,
        allowed_roots=["/Work"],
        can_read=True,
        can_write=False,
        can_delete=False,
    )
    try:
        await read_only.upload("/Work/note.txt", "synthetic example")
    except PermissionDenied:
        client.upload_inline_text.assert_not_awaited()
        print("READ_ONLY_WRITE: denied; upstream calls=0")
    else:
        raise AssertionError("Read-only write unexpectedly succeeded")

    writable = DiskService(
        client=client,
        allowed_roots=["/Work"],
        can_read=True,
        can_write=True,
        can_delete=False,
        signed_client=AsyncMock(),
    )
    try:
        await writable.upload("/Personal/note.txt", "synthetic example")
    except InvalidPath:
        client.upload_inline_text.assert_not_awaited()
        print("OUTSIDE_ALLOWED_ROOT: denied; upstream calls=0")
    else:
        raise AssertionError("Out-of-root write unexpectedly succeeded")

    await writable.upload("/Work/note.txt", "synthetic example")
    client.upload_inline_text.assert_awaited_once()
    print("ALLOWED_WRITE: accepted by mock; upstream calls=1")


if __name__ == "__main__":
    asyncio.run(main())

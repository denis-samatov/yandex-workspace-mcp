import asyncio
import os
from pathlib import Path

import pytest

from yandex_workspace_mcp.jobs.uploads import UploadJobStore
from yandex_workspace_mcp.models.errors import InvalidPath
from yandex_workspace_mcp.policies.cursors import CursorCodec
from yandex_workspace_mcp.policies.local_files import open_allowed_local_file

pytestmark = pytest.mark.skipif(
    os.name != "posix",
    reason="open_allowed_local_file() intentionally refuses all local access on non-POSIX systems",
)


@pytest.mark.asyncio
async def test_upload_store_shutdown_cancels_active_job_and_closes_descriptor(
    tmp_path: Path,
) -> None:
    source = tmp_path / "file.bin"
    source.write_bytes(b"payload")
    opened = open_allowed_local_file(str(source), [str(tmp_path)], max_bytes=100)
    started = asyncio.Event()

    async def blocked(_opened, _destination: str, _overwrite: bool) -> None:
        started.set()
        await asyncio.Event().wait()

    store = UploadJobStore(
        capacity=2,
        ttl_seconds=60,
        cursor_codec=CursorCodec((b"j" * 32,)),
    )
    created = await store.submit(
        opened,
        destination_path="/Work/file.bin",
        overwrite=False,
        runner=blocked,
    )
    await started.wait()
    await store.close()

    assert (await store.get(created.job_id)).status == "cancelled"
    with pytest.raises(InvalidPath):
        opened.verify_identity()

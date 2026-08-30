import asyncio
from pathlib import Path

import pytest

from yandex_workspace_mcp.jobs.uploads import UploadJobStore
from yandex_workspace_mcp.models.errors import InvalidPath, RateLimitExceeded
from yandex_workspace_mcp.policies.cursors import CursorCodec
from yandex_workspace_mcp.policies.local_files import open_allowed_local_file


def _opened(tmp_path: Path, name: str = "file.bin"):
    source = tmp_path / name
    source.write_bytes(b"payload")
    return open_allowed_local_file(str(source), [str(tmp_path)], max_bytes=100)


@pytest.mark.asyncio
async def test_upload_job_transitions_and_never_exposes_source_path(tmp_path: Path) -> None:
    completed = asyncio.Event()

    async def runner(opened, destination: str, overwrite: bool) -> None:
        assert opened.read() == b"payload"
        assert destination == "/Work/file.bin"
        assert overwrite is True
        completed.set()

    store = UploadJobStore(
        capacity=4,
        ttl_seconds=60,
        cursor_codec=CursorCodec((b"j" * 32,)),
    )
    created = await store.submit(
        _opened(tmp_path),
        destination_path="/Work/file.bin",
        overwrite=True,
        runner=runner,
    )
    await completed.wait()
    await asyncio.sleep(0)
    result = await store.get(created.job_id)

    assert result.status == "completed"
    assert result.bytes_sent == len(b"payload")
    assert "file_path" not in result.model_dump()
    assert str(tmp_path) not in result.model_dump_json()
    await store.close()


@pytest.mark.asyncio
async def test_store_full_does_not_evict_active_job_and_closes_rejected_handle(
    tmp_path: Path,
) -> None:
    release = asyncio.Event()

    async def blocked(_opened, _destination: str, _overwrite: bool) -> None:
        await release.wait()

    store = UploadJobStore(
        capacity=1,
        ttl_seconds=60,
        cursor_codec=CursorCodec((b"j" * 32,)),
    )
    await store.submit(
        _opened(tmp_path, "one.bin"),
        destination_path="/Work/one.bin",
        overwrite=False,
        runner=blocked,
    )
    rejected = _opened(tmp_path, "two.bin")
    with pytest.raises(RateLimitExceeded):
        await store.submit(
            rejected,
            destination_path="/Work/two.bin",
            overwrite=False,
            runner=blocked,
        )
    with pytest.raises(InvalidPath):
        rejected.verify_identity()
    release.set()
    await store.close()


@pytest.mark.asyncio
async def test_list_is_bounded_filtered_and_cursor_paginated(tmp_path: Path) -> None:
    async def done(_opened, _destination: str, _overwrite: bool) -> None:
        return None

    store = UploadJobStore(
        capacity=4,
        ttl_seconds=60,
        cursor_codec=CursorCodec((b"j" * 32,)),
    )
    for index in range(3):
        await store.submit(
            _opened(tmp_path, f"{index}.bin"),
            destination_path=f"/Work/{index}.bin",
            overwrite=False,
            runner=done,
        )
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    first = await store.list(limit=2, status="completed")
    second = await store.list(limit=2, cursor=first.next_cursor, status="completed")
    assert len(first.jobs) == 2 and first.next_cursor is not None
    assert len(second.jobs) == 1 and second.next_cursor is None
    await store.close()

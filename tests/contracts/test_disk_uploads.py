import os
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

from yandex_workspace_mcp.clients.disk import YandexDiskClient
from yandex_workspace_mcp.models.disk import DiskOperationResponse
from yandex_workspace_mcp.policies.local_files import open_allowed_local_file


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.name != "posix",
    reason="open_allowed_local_file() intentionally refuses all local access on non-POSIX systems",
)
async def test_local_upload_requests_one_link_then_one_guarded_put(tmp_path: Path) -> None:
    source = tmp_path / "payload.bin"
    source.write_bytes(b"payload")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"href": "https://uploader.disk.yandex.net/signed?secret=value", "method": "PUT"},
            request=request,
        )

    signed = AsyncMock()
    client = YandexDiskClient(
        token="token",
        client=httpx.AsyncClient(
            base_url="https://cloud-api.yandex.net/v1/disk",
            transport=httpx.MockTransport(handler),
        ),
    )
    opened = open_allowed_local_file(str(source), [str(tmp_path)], max_bytes=100)
    try:
        result = await client.upload_local_file(
            "/Work/payload.bin",
            opened,
            overwrite=True,
            signed_client=signed,
        )
    finally:
        opened.close()

    assert result == DiskOperationResponse(status="completed", path="/Work/payload.bin")
    assert len(requests) == 1
    assert dict(requests[0].url.params) == {"path": "/Work/payload.bin", "overwrite": "true"}
    signed.upload.assert_awaited_once()
    await client.close()


@pytest.mark.asyncio
async def test_inline_upload_uses_same_signed_transport() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"href": "https://uploader.disk.yandex.net/signed", "method": "PUT"},
            request=request,
        )

    signed = AsyncMock()
    client = YandexDiskClient(
        client=httpx.AsyncClient(
            base_url="https://cloud-api.yandex.net/v1/disk",
            transport=httpx.MockTransport(handler),
        ),
    )
    result = await client.upload_inline_text(
        "/Work/note.txt",
        "hello",
        overwrite=False,
        signed_client=signed,
    )

    assert result.path == "/Work/note.txt"
    signed.upload_bytes.assert_awaited_once_with(
        "https://uploader.disk.yandex.net/signed", b"hello"
    )
    await client.close()


@pytest.mark.asyncio
async def test_url_upload_sends_exact_official_request() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, request=request)

    client = YandexDiskClient(
        client=httpx.AsyncClient(
            base_url="https://cloud-api.yandex.net/v1/disk",
            transport=httpx.MockTransport(handler),
        ),
    )
    result = await client.upload_from_url(
        "https://downloads.example.test/file?signature=secret",
        "/Work/file",
        overwrite=True,
    )

    assert result.status == "completed"
    assert [(request.method, request.url.path) for request in requests] == [
        ("POST", "/v1/disk/resources/upload")
    ]
    assert dict(requests[0].url.params) == {
        "url": "https://downloads.example.test/file?signature=secret",
        "path": "/Work/file",
        "overwrite": "true",
    }
    await client.close()

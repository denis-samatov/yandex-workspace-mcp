from unittest.mock import AsyncMock

import pytest

from yandex_workspace_mcp.models.disk import DiskOperationResponse
from yandex_workspace_mcp.models.errors import PermissionDenied
from yandex_workspace_mcp.policies.urls import validate_remote_upload_url
from yandex_workspace_mcp.services.disk import DiskService


@pytest.mark.parametrize(
    "url",
    [
        "http://downloads.example.test/file",
        "https://user:pass@downloads.example.test/file",
        "https://downloads.example.test:444/file",
        "https://downloads.example.test/file#fragment",
        "https://sub.downloads.example.test/file",
        "https://downloads.example.test.evil.test/file",
        "https://127.0.0.1/file",
        "https://localhost/file",
    ],
)
def test_remote_upload_url_requires_exact_explicit_https_host(url: str) -> None:
    with pytest.raises(PermissionDenied):
        validate_remote_upload_url(url, ["downloads.example.test"])


def test_remote_upload_url_accepts_exact_host_and_preserves_query() -> None:
    value = validate_remote_upload_url(
        "https://downloads.example.test/file?signature=secret",
        ["downloads.example.test"],
    )
    assert value.endswith("?signature=secret")


@pytest.mark.asyncio
async def test_service_requires_host_allowlist_and_authorizes_destination() -> None:
    client = AsyncMock()
    client.upload_from_url.return_value = DiskOperationResponse(
        status="completed", path="/Work/file"
    )
    disabled = DiskService(client, ["/Work"], True, True, False)
    with pytest.raises(PermissionDenied):
        await disabled.upload_from_url("https://downloads.example.test/file", "/Work/file")

    enabled = DiskService(
        client,
        ["/Work"],
        True,
        True,
        False,
        upload_url_allowed_hosts=["downloads.example.test"],
    )
    result = await enabled.upload_from_url(
        "https://downloads.example.test/file?signature=secret",
        "/Work/file",
        overwrite=True,
    )
    assert result.path == "/Work/file"
    assert client.upload_from_url.await_args.kwargs["overwrite"] is True

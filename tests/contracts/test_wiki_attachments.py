import ipaddress
import os
from pathlib import Path

import httpx
import pytest

from yandex_workspace_mcp.clients.signed import SignedTransferClient, validate_signed_url
from yandex_workspace_mcp.clients.wiki import YandexWikiClient
from yandex_workspace_mcp.models.errors import InvalidInput, PermissionDenied
from yandex_workspace_mcp.models.wiki import PageLocator, WikiAttachmentUploadInput
from yandex_workspace_mcp.policies.local_files import open_allowed_local_file


@pytest.mark.parametrize(
    "url",
    [
        "http://uploader.yandex.net/file",
        "https://user@uploader.yandex.net/file",
        "https://uploader.yandex.net:444/file",
        "https://127.0.0.1/file",
        "https://evil-yandex.net/file",
        "https://uploader.yandex.net/file#fragment",
    ],
)
def test_signed_url_rejects_unsafe_shapes(url: str) -> None:
    with pytest.raises(InvalidInput):
        validate_signed_url(url, allowed_suffixes=("yandex.net",))


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.name != "posix",
    reason="open_allowed_local_file() intentionally refuses all local access on non-POSIX systems",
)
async def test_signed_upload_has_no_authorization_redirect_or_retry(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    source = allowed / "file.txt"
    source.write_bytes(b"hello")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            extensions={"network_stream": _PeerStream("8.8.8.8")},
        )

    async def resolver(host: str) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        return {ipaddress.ip_address("8.8.8.8")}

    signed = SignedTransferClient(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False),
        resolver=resolver,
    )
    opened = open_allowed_local_file(str(source), [str(allowed)], max_bytes=100)
    try:
        await signed.upload("https://uploader.yandex.net/file?signature=secret", opened)
    finally:
        opened.close()
        await signed.close()

    assert len(requests) == 1
    assert requests[0].headers.get("Authorization") is None
    assert requests[0].read() == b"hello"


@pytest.mark.asyncio
async def test_signed_transfer_rejects_private_mixed_and_peer_mismatch() -> None:
    async def private(host: str):
        return {ipaddress.ip_address("10.0.0.1")}

    signed = SignedTransferClient(
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200))),
        resolver=private,
    )
    with pytest.raises(PermissionDenied):
        await signed.validate("https://uploader.yandex.net/file")
    await signed.close()


class _PeerStream:
    def __init__(self, peer: str) -> None:
        self.peer = peer

    def get_extra_info(self, name: str):
        if name == "server_addr":
            return (self.peer, 443)
        return None


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.name != "posix",
    reason="open_allowed_local_file() intentionally refuses all local access on non-POSIX systems",
)
async def test_wiki_attachment_uses_open_handle_and_exact_session_flow(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    source = allowed / "file.txt"
    source.write_bytes(b"hello")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "PUT":
            assert await request.aread() == b"hello"
            return httpx.Response(200, json={})
        if request.url.path.endswith("/finish"):
            return httpx.Response(200, json={})
        if request.url.path.endswith("/attachments"):
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": 3,
                            "name": "file.txt",
                            "download_url": "https://wiki.yandex.ru/Team/Page/.files/file.txt?secret=x",
                        }
                    ]
                },
            )
        if request.url.path.endswith("/append-content"):
            return httpx.Response(200, json={"id": 42, "slug": "Team/Page"})
        return httpx.Response(200, json={"session_id": "session"})

    client = YandexWikiClient(
        client=httpx.AsyncClient(
            base_url="https://api.wiki.yandex.net/v1",
            transport=httpx.MockTransport(handler),
        )
    )
    opened = open_allowed_local_file(str(source), [str(allowed)], max_bytes=100)
    try:
        result = await client.upload_attachment(
            42,
            opened,
            WikiAttachmentUploadInput(
                locator=PageLocator(page_id=42),
                file_path="ignored-after-open",
                append_markup=True,
            ),
        )
    finally:
        opened.close()
        await client.close()

    assert [(request.method, request.url.path) for request in requests] == [
        ("POST", "/v1/upload_sessions"),
        ("PUT", "/v1/upload_sessions/session/upload_part"),
        ("POST", "/v1/upload_sessions/session/finish"),
        ("POST", "/v1/pages/42/attachments"),
        ("POST", "/v1/pages/42/append-content"),
    ]
    assert dict(requests[1].url.params) == {"part_number": "1"}
    assert result.page_id == 42
    assert result.appended_markup is True
    assert "?secret=" not in (result.appended_content or "")

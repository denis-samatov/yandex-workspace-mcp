import ipaddress

import httpx
import pytest

from yandex_workspace_mcp.clients.signed import (
    SignedTransferClient,
    _PinnedNetworkBackend,
    validate_signed_url,
)
from yandex_workspace_mcp.models.errors import InvalidInput, PermissionDenied


class _PeerStream:
    def __init__(self, peer: str) -> None:
        self.peer = peer

    def get_extra_info(self, name: str):
        return (self.peer, 443) if name == "server_addr" else None


async def _public(_host: str):
    return {ipaddress.ip_address("8.8.8.8")}


@pytest.mark.parametrize(
    "url",
    [
        "http://downloader.disk.yandex.net/file",
        "https://user:pass@downloader.disk.yandex.net/file",
        "https://downloader.disk.yandex.net:444/file",
        "https://127.0.0.1/file",
        "https://[::ffff:127.0.0.1]/file",
        "https://downloader.disk.yandex.net/file#fragment",
        "https://downloader.disk.yandex.net.evil.test/file",
    ],
)
def test_signed_url_shape_is_strict(url: str) -> None:
    with pytest.raises(InvalidInput):
        validate_signed_url(url)


@pytest.mark.asyncio
async def test_signed_validation_rejects_mixed_public_private_dns() -> None:
    async def mixed(_host: str):
        return {ipaddress.ip_address("8.8.8.8"), ipaddress.ip_address("10.0.0.1")}

    client = SignedTransferClient(
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200))),
        resolver=mixed,
    )
    with pytest.raises(PermissionDenied):
        await client.validate("https://downloader.disk.yandex.net/file?secret=value")
    await client.close()


@pytest.mark.asyncio
async def test_signed_download_is_tokenless_peer_checked_and_bounded() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            content=b"hello",
            headers={"Content-Length": "5"},
            extensions={"network_stream": _PeerStream("8.8.8.8")},
            request=request,
        )

    client = SignedTransferClient(
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            headers={"Authorization": "Bearer must-not-leak"},
            follow_redirects=False,
        ),
        resolver=_public,
    )
    assert (
        await client.download("https://downloader.disk.yandex.net/file?secret=value", max_bytes=5)
        == b"hello"
    )
    assert requests[0].headers.get("Authorization") is None
    await client.close()


@pytest.mark.asyncio
async def test_signed_download_rejects_redirect_peer_mismatch_and_oversize() -> None:
    responses = iter(
        [
            httpx.Response(302, headers={"Location": "https://evil.test/"}),
            httpx.Response(
                200,
                content=b"ok",
                extensions={"network_stream": _PeerStream("1.1.1.1")},
            ),
            httpx.Response(
                200,
                content=b"too large",
                headers={"Content-Length": "9"},
                extensions={"network_stream": _PeerStream("8.8.8.8")},
            ),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        response = next(responses)
        response.request = request
        return response

    client = SignedTransferClient(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False),
        resolver=_public,
    )
    for _ in range(3):
        with pytest.raises(PermissionDenied):
            await client.download(
                "https://downloader.disk.yandex.net/file?secret=value", max_bytes=5
            )
    await client.close()


@pytest.mark.asyncio
async def test_signed_upload_streams_and_rejects_oversized_response_body() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"response-too-large",
            extensions={"network_stream": _PeerStream("8.8.8.8")},
            request=request,
        )

    client = SignedTransferClient(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        resolver=_public,
        max_response_bytes=4,
    )
    with pytest.raises(PermissionDenied):
        await client.upload_bytes(
            "https://uploader.yandex.net/file?signature=secret",
            b"upload",
        )
    await client.close()


class _CoreStream:
    def __init__(self, peer: str) -> None:
        self.peer = peer
        self.closed = False

    def get_extra_info(self, name: str):
        return (self.peer, 443) if name == "server_addr" else None

    async def aclose(self) -> None:
        self.closed = True


class _CoreBackend:
    def __init__(self, stream: _CoreStream) -> None:
        self.stream = stream
        self.connected_host: str | None = None

    async def connect_tcp(self, host: str, port: int, **_kwargs):
        self.connected_host = host
        return self.stream


@pytest.mark.asyncio
async def test_default_backend_pins_validated_ip_before_http_bytes() -> None:
    stream = _CoreStream("8.8.8.8")
    delegate = _CoreBackend(stream)
    backend = _PinnedNetworkBackend(
        hostname="downloader.disk.yandex.net",
        addresses={ipaddress.ip_address("8.8.8.8")},
        delegate=delegate,
    )

    assert await backend.connect_tcp("downloader.disk.yandex.net", 443) is stream
    assert delegate.connected_host == "8.8.8.8"

    mismatch = _CoreStream("1.1.1.1")
    backend = _PinnedNetworkBackend(
        hostname="downloader.disk.yandex.net",
        addresses={ipaddress.ip_address("8.8.8.8")},
        delegate=_CoreBackend(mismatch),
    )
    with pytest.raises(PermissionDenied):
        await backend.connect_tcp("downloader.disk.yandex.net", 443)
    assert mismatch.closed is True

import httpx
import pytest

from yandex_workspace_mcp.clients.base import RequestCredentials
from yandex_workspace_mcp.clients.disk import YandexDiskClient
from yandex_workspace_mcp.models.errors import ContractMismatchError, ResourceNotFound


def _client(handler) -> YandexDiskClient:
    return YandexDiskClient(
        client=httpx.AsyncClient(
            base_url="https://cloud-api.yandex.net/v1/disk",
            transport=httpx.MockTransport(handler),
        )
    )


@pytest.mark.asyncio
async def test_disk_read_methods_use_exact_endpoints_and_typed_outputs() -> None:
    requests: list[httpx.Request] = []
    responses = iter(
        [
            {
                "total_space": 100,
                "used_space": 25,
                "trash_size": 2,
                "max_file_size": 50,
                "system_folders": {},
                "wire_only": True,
            },
            {
                "name": "Work",
                "path": "disk:/Work",
                "type": "dir",
                "_embedded": {
                    "items": [{"name": "a.txt", "path": "disk:/Work/a.txt", "type": "file"}],
                    "limit": 25,
                    "offset": 5,
                    "total": 1,
                },
            },
            {
                "items": [{"name": "new.txt", "path": "disk:/Work/new.txt", "type": "file"}],
                "limit": 10,
                "offset": 0,
                "total": 1,
            },
            {"name": "a.txt", "path": "disk:/Work/a.txt", "type": "file"},
            {"href": "https://downloader.disk.yandex.net/signed?token=secret", "method": "GET"},
        ]
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=next(responses), request=request)

    client = _client(handler)
    credentials = RequestCredentials(token="per-request")
    info = await client.info(credentials=credentials)
    listed = await client.list_resources(
        "/Work", limit=25, offset=5, sort="-modified", credentials=credentials
    )
    recent = await client.recent(limit=10, media_type="document", credentials=credentials)
    metadata = await client.get_metadata("/Work/a.txt", credentials=credentials)
    link = await client.get_download_link("/Work/a.txt", credentials=credentials)

    assert info.total_space == 100
    assert listed.embedded is not None and listed.embedded.items[0].path == "/Work/a.txt"
    assert recent.items[0].path == "/Work/new.txt"
    assert metadata.path == "/Work/a.txt"
    assert str(link.download_url).startswith("https://downloader.disk.yandex.net/")
    assert [request.url.path for request in requests] == [
        "/v1/disk",
        "/v1/disk/resources",
        "/v1/disk/resources/last-uploaded",
        "/v1/disk/resources",
        "/v1/disk/resources/download",
    ]
    assert dict(requests[1].url.params) == {
        "path": "/Work",
        "limit": "25",
        "offset": "5",
        "sort": "-modified",
    }
    assert requests[0].headers["Authorization"] == "OAuth per-request"
    await client.close()


@pytest.mark.asyncio
async def test_disk_read_404_and_malformed_success_are_translated() -> None:
    async def missing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={}, request=request)

    client = _client(missing)
    with pytest.raises(ResourceNotFound):
        await client.get_metadata("/missing")
    await client.close()

    async def malformed(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True}, request=request)

    client = _client(malformed)
    with pytest.raises(ContractMismatchError):
        await client.info()
    await client.close()

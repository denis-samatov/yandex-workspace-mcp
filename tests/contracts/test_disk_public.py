import httpx
import pytest

from yandex_workspace_mcp.clients.disk import YandexDiskClient


@pytest.mark.asyncio
async def test_public_clients_use_exact_endpoints_and_drop_signed_fields() -> None:
    requests: list[httpx.Request] = []
    responses = iter(
        [
            httpx.Response(200),
            httpx.Response(200),
            httpx.Response(
                200,
                json={
                    "name": "Public",
                    "type": "dir",
                    "file": "https://signed.invalid/secret",
                    "_embedded": {
                        "items": [{"name": "a.txt", "type": "file", "file": "https://secret"}],
                        "limit": 10,
                        "offset": 5,
                    },
                },
            ),
        ]
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        response = next(responses)
        response.request = request
        return response

    client = YandexDiskClient(
        client=httpx.AsyncClient(
            base_url="https://cloud-api.yandex.net/v1/disk",
            transport=httpx.MockTransport(handler),
        )
    )
    published = await client.publish_resource("/Work/Public")
    unpublished = await client.unpublish_resource("/Work/Public")
    public = await client.get_public_resource(
        public_key="key",
        path="/nested",
        limit=10,
        offset=5,
    )

    assert published.status == unpublished.status == "completed"
    assert public.embedded is not None and public.embedded.items[0].name == "a.txt"
    assert "file" not in public.model_dump()
    assert "file" not in public.embedded.items[0].model_dump()
    assert [(request.method, request.url.path) for request in requests] == [
        ("PUT", "/v1/disk/resources/publish"),
        ("PUT", "/v1/disk/resources/unpublish"),
        ("GET", "/v1/disk/public/resources"),
    ]
    assert dict(requests[2].url.params) == {
        "public_key": "key",
        "path": "/nested",
        "limit": "10",
        "offset": "5",
    }
    await client.close()

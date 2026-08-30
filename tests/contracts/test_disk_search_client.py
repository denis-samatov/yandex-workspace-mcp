import importlib

import httpx
import pytest


def test_disk_list_files_method_exists() -> None:
    module = importlib.import_module("yandex_workspace_mcp.clients.disk")
    assert hasattr(module.YandexDiskClient, "list_files")


@pytest.mark.asyncio
async def test_list_files_uses_exact_query_and_typed_mapping() -> None:
    module = importlib.import_module("yandex_workspace_mcp.clients.disk")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "name": "report.md",
                        "path": "disk:/Work/report.md",
                        "type": "file",
                        "new": "ignored",
                    }
                ],
                "limit": 100,
                "offset": 25,
                "new_envelope": True,
            },
            request=request,
        )

    client = module.YandexDiskClient(
        token="token",
        client=httpx.AsyncClient(
            base_url="https://cloud-api.yandex.net/v1/disk",
            transport=httpx.MockTransport(handler),
        ),
        signed_url_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    page = await client.list_files(
        limit=100,
        offset=25,
        media_type="document,text",
    )

    assert requests[0].url.path == "/v1/disk/resources/files"
    assert dict(requests[0].url.params) == {
        "limit": "100",
        "offset": "25",
        "media_type": "document,text",
    }
    assert page.items[0].path == "/Work/report.md"
    assert "new" not in page.model_dump_json()
    await client.close()

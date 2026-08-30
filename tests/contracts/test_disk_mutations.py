import httpx
import pytest

from yandex_workspace_mcp.clients.disk import YandexDiskClient
from yandex_workspace_mcp.models.errors import UpstreamUnavailable


@pytest.mark.asyncio
async def test_disk_mutations_use_exact_methods_params_and_typed_results() -> None:
    requests: list[httpx.Request] = []
    statuses = iter([201, 204, 201, 201])

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(next(statuses), request=request)

    client = YandexDiskClient(
        token="token",
        client=httpx.AsyncClient(
            base_url="https://cloud-api.yandex.net/v1/disk",
            transport=httpx.MockTransport(handler),
        ),
    )

    created = await client.create_folder("/Work/new")
    deleted = await client.delete_resource("/Work/old", permanently=False)
    copied = await client.copy_resource("/Work/a", "/Work/b", overwrite=True)
    moved = await client.move_resource("/Work/b", "/Work/c", overwrite=False)

    assert {created.status, deleted.status, copied.status, moved.status} == {"completed"}
    assert [(request.method, request.url.path) for request in requests] == [
        ("PUT", "/v1/disk/resources"),
        ("DELETE", "/v1/disk/resources"),
        ("POST", "/v1/disk/resources/copy"),
        ("POST", "/v1/disk/resources/move"),
    ]
    assert dict(requests[2].url.params) == {
        "from": "/Work/a",
        "path": "/Work/b",
        "overwrite": "true",
    }
    await client.close()


@pytest.mark.asyncio
async def test_disk_mutation_transport_failure_is_not_retried() -> None:
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("ambiguous", request=request)

    client = YandexDiskClient(
        token="token",
        client=httpx.AsyncClient(
            base_url="https://cloud-api.yandex.net/v1/disk",
            transport=httpx.MockTransport(handler),
        ),
    )
    with pytest.raises(UpstreamUnavailable):
        await client.copy_resource("/Work/a", "/Work/b")
    assert attempts == 1
    await client.close()

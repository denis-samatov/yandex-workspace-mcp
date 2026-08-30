from unittest.mock import AsyncMock

import pytest

from yandex_workspace_mcp.models.disk import DiskPublicResource, DiskResourcePage
from yandex_workspace_mcp.models.errors import InvalidPath, PermissionDenied
from yandex_workspace_mcp.services.disk import DiskService


def _service(allowlist: list[str]) -> tuple[DiskService, AsyncMock]:
    client = AsyncMock()
    client.get_public_resource.return_value = DiskPublicResource(
        name="Public",
        type="dir",
        embedded=DiskResourcePage(limit=100, offset=0),
    )
    return (
        DiskService(
            client,
            ["/Work"],
            True,
            True,
            False,
            allowed_public_keys=allowlist,
        ),
        client,
    )


@pytest.mark.asyncio
async def test_public_lookup_is_absent_by_policy_and_denials_do_not_leak_locator() -> None:
    service, client = _service([])
    with pytest.raises(PermissionDenied) as error:
        await service.get_public_resource(public_key="secret-key")
    assert "secret-key" not in str(error.value)
    client.get_public_resource.assert_not_awaited()


@pytest.mark.asyncio
async def test_public_key_and_normalized_url_require_exact_allowlist_match() -> None:
    service, client = _service(["exact-key", "https://disk.yandex.ru/d/abc"])

    await service.get_public_resource(public_key="exact-key", path="/nested")
    await service.get_public_resource(public_url="https://DISK.YANDEX.RU/d/abc/")
    with pytest.raises(PermissionDenied):
        await service.get_public_resource(public_key="exact-key-suffix")

    assert client.get_public_resource.await_count == 2


@pytest.mark.asyncio
async def test_publish_and_unpublish_still_enforce_private_disk_roots() -> None:
    service, client = _service(["key"])
    with pytest.raises(InvalidPath):
        await service.publish("/Other/Public")
    client.publish_resource.assert_not_awaited()

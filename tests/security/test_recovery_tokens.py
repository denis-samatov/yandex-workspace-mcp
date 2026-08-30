import asyncio
import base64
from unittest.mock import AsyncMock

import pytest
from pydantic import SecretStr, ValidationError

from yandex_workspace_mcp.auth.recovery import InMemoryRecoveryTokenStore, SharedRecoveryTokenStore
from yandex_workspace_mcp.auth.stores import InMemoryTokenStore
from yandex_workspace_mcp.config import Settings
from yandex_workspace_mcp.models.errors import ResourceNotFound
from yandex_workspace_mcp.models.wiki import (
    PageDeleteInput,
    PageLocator,
    PageRecoverInput,
    PageRecoverResponse,
    WikiPage,
)
from yandex_workspace_mcp.services.wiki import WikiService


def _key(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


@pytest.mark.asyncio
async def test_store_returns_random_handle_and_encrypts_upstream_token_at_rest() -> None:
    store = InMemoryRecoveryTokenStore((b"k" * 32,))
    handle = await store.put(
        upstream_token="upstream-secret-token",
        principal_id="principal-a",
        normalized_locator="Team/Page",
    )

    assert handle != "upstream-secret-token"
    assert len(handle) >= 32
    assert "upstream-secret-token" not in repr(store._records)

    consumed = await store.consume(handle, principal_id="principal-a")
    assert consumed.upstream_token == "upstream-secret-token"
    assert consumed.normalized_locator == "Team/Page"


@pytest.mark.asyncio
async def test_unknown_expired_consumed_and_cross_principal_are_indistinguishable() -> None:
    now = [100.0]
    store = InMemoryRecoveryTokenStore((b"k" * 32,), clock=lambda: now[0], ttl_seconds=900)
    handle = await store.put(
        upstream_token="token", principal_id="principal-a", normalized_locator="Team/Page"
    )

    for candidate, principal in [("unknown", "principal-a"), (handle, "principal-b")]:
        with pytest.raises(ResourceNotFound) as caught:
            await store.consume(candidate, principal_id=principal)
        assert str(caught.value) == str(ResourceNotFound())

    await store.consume(handle, principal_id="principal-a")
    with pytest.raises(ResourceNotFound):
        await store.consume(handle, principal_id="principal-a")

    expired = await store.put(
        upstream_token="later", principal_id="principal-a", normalized_locator="Team/Page"
    )
    now[0] += 901
    with pytest.raises(ResourceNotFound):
        await store.consume(expired, principal_id="principal-a")


@pytest.mark.asyncio
async def test_consume_is_atomic_under_concurrency() -> None:
    store = InMemoryRecoveryTokenStore((b"k" * 32,))
    handle = await store.put(
        upstream_token="token", principal_id="principal", normalized_locator="Team/Page"
    )

    results = await asyncio.gather(
        *[store.consume(handle, principal_id="principal") for _ in range(10)],
        return_exceptions=True,
    )
    assert sum(not isinstance(result, BaseException) for result in results) == 1
    assert sum(isinstance(result, ResourceNotFound) for result in results) == 9


@pytest.mark.asyncio
async def test_key_rotation_decrypts_records_written_with_old_primary() -> None:
    records: dict[str, object] = {}
    old = InMemoryRecoveryTokenStore((b"o" * 32,), records=records)
    handle = await old.put(
        upstream_token="token", principal_id="principal", normalized_locator="Team/Page"
    )
    rotated = InMemoryRecoveryTokenStore((b"n" * 32, b"o" * 32), records=records)

    record = await rotated.consume(handle, principal_id="principal")
    assert record.upstream_token == "token"


@pytest.mark.asyncio
async def test_shared_recovery_store_survives_replica_restart_and_is_user_bound() -> None:
    records: dict[str, object] = {}
    backend_a = InMemoryTokenStore((b"k" * 32,), clock=lambda: 100.0, records=records)
    first = SharedRecoveryTokenStore(backend_a, clock=lambda: 100.0)
    handle = await first.put(
        upstream_token="upstream-secret",
        principal_id="principal-a",
        normalized_locator="Team/Page",
    )

    backend_b = InMemoryTokenStore((b"k" * 32,), clock=lambda: 100.0, records=records)
    second = SharedRecoveryTokenStore(backend_b, clock=lambda: 100.0)
    with pytest.raises(ResourceNotFound):
        await second.consume(handle, principal_id="principal-b")
    recovered = await second.consume(handle, principal_id="principal-a")

    assert recovered.upstream_token == "upstream-secret"
    assert recovered.normalized_locator == "Team/Page"


def test_remote_delete_requires_explicit_valid_encryption_key_ring() -> None:
    with pytest.raises(ValidationError):
        Settings(
            mcp_transport="streamable-http",
            wiki_delete=True,
            mcp_token_encryption_keys=[],
        )
    with pytest.raises(ValidationError):
        Settings(
            mcp_transport="streamable-http",
            wiki_delete=True,
            mcp_token_encryption_keys=[SecretStr(_key(b"short"))],
        )

    settings = Settings(
        mcp_transport="streamable-http",
        wiki_delete=True,
        mcp_token_encryption_keys=[
            SecretStr(_key(b"a" * 32)),
            SecretStr(_key(b"b" * 32)),
        ],
    )
    assert len(settings.mcp_token_encryption_keys) == 2


@pytest.mark.asyncio
async def test_service_delete_and_recover_never_expose_upstream_token() -> None:
    client = AsyncMock()
    client.get_page.return_value = WikiPage(id=42, slug="Team/Page")
    client.delete_page.return_value = "raw-upstream-recovery-token"
    client.recover_page.return_value = PageRecoverResponse(id=42, slug="Team/Page")
    store = InMemoryRecoveryTokenStore((b"k" * 32,))
    service = WikiService(client, ["/Team"], True, True, True, recovery_store=store)

    deleted = await service.delete_page(
        PageDeleteInput(locator=PageLocator(page_id=42)), principal_id="principal"
    )
    assert deleted.recovery_token
    assert deleted.recovery_token != "raw-upstream-recovery-token"

    recovered = await service.recover_page(
        PageRecoverInput(recovery_token=deleted.recovery_token), principal_id="principal"
    )
    assert recovered.id == 42
    client.recover_page.assert_awaited_once_with("raw-upstream-recovery-token", credentials=None)

    with pytest.raises(ResourceNotFound):
        await service.recover_page(
            PageRecoverInput(recovery_token=deleted.recovery_token), principal_id="principal"
        )

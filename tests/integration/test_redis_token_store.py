import asyncio
import base64
import os
import uuid

import pytest

from yandex_workspace_mcp.auth.models import (
    AccessTokenRecord,
    AuthorizationCodeRecord,
    OAuthStateRecord,
    RefreshTokenRecord,
)
from yandex_workspace_mcp.auth.recovery import SharedRecoveryTokenStore
from yandex_workspace_mcp.auth.stores import TokenStoreMiss
from yandex_workspace_mcp.models.errors import ResourceNotFound

REDIS_URL = os.getenv("TEST_REDIS_URL")
pytestmark = pytest.mark.skipif(
    not REDIS_URL, reason="TEST_REDIS_URL is not configured; Redis contract test is opt-in"
)


@pytest.mark.asyncio
async def test_redis_state_is_encrypted_and_single_use() -> None:
    pytest.importorskip("redis")
    from yandex_workspace_mcp.auth.redis_store import RedisTokenStore

    key = base64.urlsafe_b64decode(base64.urlsafe_b64encode(b"r" * 32))
    store = RedisTokenStore((key,), url=REDIS_URL, prefix=f"ywmcp:test:{uuid.uuid4().hex}")
    await store.open()
    record = OAuthStateRecord(
        client_id="client",
        redirect_uri="http://127.0.0.1/callback",
        scopes=("workspace:read",),
        code_challenge="challenge",
        resource=None,
        expires_at=store._clock() + 30,
    )
    try:
        await store.put_state("state-secret", record)
        assert await store.consume_state("state-secret") == record
        with pytest.raises(TokenStoreMiss):
            await store.consume_state("state-secret")
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_redis_codes_rotation_and_recovery_are_atomic_across_replicas() -> None:
    pytest.importorskip("redis")
    from yandex_workspace_mcp.auth.redis_store import RedisTokenStore

    prefix = f"ywmcp:test:{uuid.uuid4().hex}"
    first = RedisTokenStore((b"r" * 32,), url=REDIS_URL, prefix=prefix, clock=lambda: 100.0)
    second = RedisTokenStore((b"r" * 32,), url=REDIS_URL, prefix=prefix, clock=lambda: 100.0)
    await first.open()
    await second.open()
    try:
        code = AuthorizationCodeRecord(
            client_id="client",
            redirect_uri="https://client.example/callback",
            scopes=("workspace:read",),
            code_challenge="challenge",
            resource="https://mcp.example",
            subject="principal",
            expires_at=200,
        )
        await first.put_authorization_code("code", code)
        code_results = await asyncio.gather(
            first.consume_authorization_code("code"),
            second.consume_authorization_code("code"),
            return_exceptions=True,
        )
        assert sum(result == code for result in code_results) == 1
        assert sum(isinstance(result, TokenStoreMiss) for result in code_results) == 1

        old_access = AccessTokenRecord(
            client_id="client",
            scopes=("workspace:read",),
            subject="principal",
            resource="https://mcp.example",
            expires_at=200,
            refresh_token="refresh-old",
        )
        old_refresh = RefreshTokenRecord(
            client_id="client",
            scopes=("workspace:read",),
            subject="principal",
            expires_at=300,
            access_token="access-old",
        )
        await first.put_token_pair(
            access_token="access-old",
            access_record=old_access,
            refresh_token="refresh-old",
            refresh_record=old_refresh,
        )
        new_access = old_access.model_copy(update={"refresh_token": "refresh-new"})
        new_refresh = old_refresh.model_copy(update={"access_token": "access-new"})
        rotations = await asyncio.gather(
            *[
                store.rotate_token_pair(
                    old_refresh_token="refresh-old",
                    new_refresh_token="refresh-new",
                    new_refresh_record=new_refresh,
                    new_access_token="access-new",
                    new_access_record=new_access,
                )
                for store in (first, second)
            ],
            return_exceptions=True,
        )
        assert sum(result == old_refresh for result in rotations) == 1
        assert sum(isinstance(result, TokenStoreMiss) for result in rotations) == 1
        with pytest.raises(TokenStoreMiss):
            await first.get_access_token("access-old")
        assert await second.get_access_token("access-new") == new_access

        recovery_a = SharedRecoveryTokenStore(first, clock=lambda: 100.0)
        recovery_b = SharedRecoveryTokenStore(second, clock=lambda: 100.0)
        handle = await recovery_a.put(
            upstream_token="upstream",
            principal_id="principal",
            normalized_locator="Team/Page",
        )
        with pytest.raises(ResourceNotFound):
            await recovery_b.consume(handle, principal_id="other")
        assert (
            await recovery_b.consume(handle, principal_id="principal")
        ).upstream_token == "upstream"
    finally:
        await first.close()
        await second.close()


@pytest.mark.asyncio
async def test_redis_key_rotation_reads_old_ciphertext() -> None:
    pytest.importorskip("redis")
    from yandex_workspace_mcp.auth.redis_store import RedisTokenStore

    prefix = f"ywmcp:test:{uuid.uuid4().hex}"
    old = RedisTokenStore((b"o" * 32,), url=REDIS_URL, prefix=prefix, clock=lambda: 100.0)
    rotated = RedisTokenStore(
        (b"n" * 32, b"o" * 32), url=REDIS_URL, prefix=prefix, clock=lambda: 100.0
    )
    await old.open()
    await rotated.open()
    state = OAuthStateRecord(
        client_id="client",
        redirect_uri="https://client.example/callback",
        scopes=("workspace:read",),
        code_challenge="challenge",
        resource=None,
        expires_at=200,
    )
    try:
        await old.put_state("state", state)
        assert await rotated.consume_state("state") == state
    finally:
        await old.close()
        await rotated.close()

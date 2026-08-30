import asyncio

import pytest

from yandex_workspace_mcp.auth.models import (
    AccessTokenRecord,
    AuthorizationCodeRecord,
    OAuthStateRecord,
    RefreshTokenRecord,
)
from yandex_workspace_mcp.auth.stores import InMemoryTokenStore, TokenStoreMiss


@pytest.mark.asyncio
async def test_state_and_authorization_code_are_single_use_under_race() -> None:
    store = InMemoryTokenStore((b"k" * 32,), clock=lambda: 100.0)
    state = OAuthStateRecord(
        client_id="client",
        redirect_uri="https://client.example/cb",
        scopes=("workspace:read",),
        code_challenge="challenge",
        resource="https://mcp.example",
        expires_at=200,
    )
    await store.put_state("state-secret", state)
    outcomes = await asyncio.gather(
        *[store.consume_state("state-secret") for _ in range(8)], return_exceptions=True
    )
    assert sum(isinstance(value, OAuthStateRecord) for value in outcomes) == 1
    assert sum(isinstance(value, TokenStoreMiss) for value in outcomes) == 7

    code = AuthorizationCodeRecord(
        client_id="client",
        redirect_uri="https://client.example/cb",
        scopes=("workspace:read",),
        code_challenge="challenge",
        resource="https://mcp.example",
        subject="principal",
        expires_at=200,
    )
    await store.put_authorization_code("code-secret", code)
    assert await store.consume_authorization_code("code-secret") == code
    with pytest.raises(TokenStoreMiss):
        await store.consume_authorization_code("code-secret")


@pytest.mark.asyncio
async def test_access_refresh_rotation_and_pair_revocation_are_atomic() -> None:
    store = InMemoryTokenStore((b"k" * 32,), clock=lambda: 100.0)
    access = AccessTokenRecord(
        client_id="client",
        scopes=("workspace:read",),
        subject="principal",
        resource="https://mcp.example",
        expires_at=200,
        refresh_token="refresh-old",
    )
    refresh = RefreshTokenRecord(
        client_id="client",
        scopes=("workspace:read",),
        subject="principal",
        expires_at=300,
        access_token="access-old",
    )
    await store.put_access_token("access-old", access)
    await store.put_refresh_token("refresh-old", refresh)

    rotated = refresh.model_copy(update={"access_token": "access-new"})
    new_access = access.model_copy(update={"refresh_token": "refresh-new"})
    assert (
        await store.rotate_token_pair(
            old_refresh_token="refresh-old",
            new_refresh_token="refresh-new",
            new_refresh_record=rotated,
            new_access_token="access-new",
            new_access_record=new_access,
        )
        == refresh
    )
    with pytest.raises(TokenStoreMiss):
        await store.get_refresh_token("refresh-old")
    with pytest.raises(TokenStoreMiss):
        await store.get_access_token("access-old")
    assert await store.get_access_token("access-new") == new_access
    await store.revoke_token_pair(access_token="access-new", refresh_token="refresh-new")
    with pytest.raises(TokenStoreMiss):
        await store.get_access_token("access-new")
    with pytest.raises(TokenStoreMiss):
        await store.get_refresh_token("refresh-new")


@pytest.mark.asyncio
async def test_expiry_and_close_are_deterministic_and_idempotent() -> None:
    now = [100.0]
    store = InMemoryTokenStore((b"k" * 32,), clock=lambda: now[0])
    record = AccessTokenRecord(
        client_id="client",
        scopes=(),
        subject="principal",
        resource=None,
        expires_at=101,
    )
    await store.put_access_token("token", record)
    now[0] = 102
    with pytest.raises(TokenStoreMiss):
        await store.get_access_token("token")
    await store.close()
    await store.close()
    with pytest.raises(TokenStoreMiss):
        await store.get_access_token("token")

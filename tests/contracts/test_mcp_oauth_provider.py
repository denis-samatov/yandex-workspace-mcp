import base64
import hashlib
from urllib.parse import parse_qs, urlsplit

import pytest
from mcp.server.auth.provider import AuthorizationParams, RegistrationError, TokenError
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl

from yandex_workspace_mcp.auth.models import DownstreamCredentialRecord
from yandex_workspace_mcp.auth.oauth import YandexMcpOAuthProvider
from yandex_workspace_mcp.auth.stores import InMemoryTokenStore, TokenStoreMiss


def _client(**updates) -> OAuthClientInformationFull:
    values = {
        "client_id": "client-id",
        "client_secret": "client-secret",
        "redirect_uris": ["https://client.example/callback"],
        "scope": "workspace:read workspace:write",
        "token_endpoint_auth_method": "client_secret_post",
    }
    values.update(updates)
    return OAuthClientInformationFull.model_validate(values)


@pytest.mark.asyncio
async def test_full_authorization_code_refresh_and_revocation_contract() -> None:
    now = [100.0]
    store = InMemoryTokenStore((b"k" * 32,), clock=lambda: now[0])
    provider = YandexMcpOAuthProvider(
        store=store,
        issuer_url="https://mcp.example",
        resource_server_url="https://mcp.example",
        yandex_client_id="yandex-client",
        yandex_callback_url="https://mcp.example/oauth/yandex/callback",
        valid_scopes=["workspace:read", "workspace:write"],
        clock=lambda: now[0],
    )
    client = _client()
    await provider.register_client(client)
    loaded_client = await provider.get_client("client-id")
    assert loaded_client is not None
    assert loaded_client.client_secret == "client-secret"

    verifier = "v" * 48
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    redirect = await provider.authorize(
        client,
        AuthorizationParams(
            state="client-state",
            scopes=["workspace:read"],
            code_challenge=challenge,
            redirect_uri=AnyUrl("https://client.example/callback"),
            redirect_uri_provided_explicitly=True,
            resource="https://mcp.example",
        ),
    )
    query = parse_qs(urlsplit(redirect).query)
    assert urlsplit(redirect).netloc == "oauth.yandex.ru"
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["yandex-client"]
    assert query["code_challenge_method"] == ["S256"]

    client_redirect = await provider.complete_authorization(query["state"][0], "yandex-subject")
    completed = parse_qs(urlsplit(client_redirect).query)
    assert completed["state"] == ["client-state"]
    code_value = completed["code"][0]

    code = await provider.load_authorization_code(client, code_value)
    assert code is not None
    assert code.subject and code.subject != "yandex-subject"
    # Loading is intentionally non-destructive: SDK PKCE/redirect validation happens next.
    assert await provider.load_authorization_code(client, code_value) is not None

    token = await provider.exchange_authorization_code(client, code)
    assert await provider.load_authorization_code(client, code_value) is None
    with pytest.raises(TokenError):
        await provider.exchange_authorization_code(client, code)
    assert len(token.access_token) >= 27
    assert token.refresh_token and len(token.refresh_token) >= 27
    access = await provider.load_access_token(token.access_token)
    assert access is not None
    assert access.resource == "https://mcp.example"

    refresh = await provider.load_refresh_token(client, token.refresh_token)
    assert refresh is not None
    narrowed = await provider.exchange_refresh_token(client, refresh, ["workspace:read"])
    assert narrowed.refresh_token is not None
    assert narrowed.refresh_token != token.refresh_token
    assert narrowed.scope == "workspace:read"
    assert await provider.load_refresh_token(client, token.refresh_token) is None

    narrowed_access = await provider.load_access_token(narrowed.access_token)
    assert narrowed_access is not None
    assert narrowed_access.subject is not None
    await store.put_downstream(
        narrowed_access.subject,
        DownstreamCredentialRecord(
            principal_id=narrowed_access.subject,
            access_token="yandex-secret",
            expires_at=200,
        ),
    )
    await provider.revoke_token(narrowed_access)
    assert await provider.load_access_token(narrowed.access_token) is None
    assert await provider.load_refresh_token(client, narrowed.refresh_token) is None
    with pytest.raises(TokenStoreMiss):
        await store.get_downstream(narrowed_access.subject)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "redirect_uri",
    [
        "http://public.example/callback",
        "https://user:pass@client.example/callback",
        "https://client.example/callback#fragment",
        "https://*.example/callback",
    ],
)
async def test_dynamic_registration_rejects_unsafe_redirects(redirect_uri: str) -> None:
    provider = YandexMcpOAuthProvider(
        store=InMemoryTokenStore((b"k" * 32,)),
        issuer_url="https://mcp.example",
        resource_server_url="https://mcp.example",
        yandex_client_id="yandex-client",
        yandex_callback_url="https://mcp.example/oauth/yandex/callback",
        valid_scopes=["workspace:read", "workspace:write"],
    )
    with pytest.raises(RegistrationError):
        await provider.register_client(_client(redirect_uris=[redirect_uri]))


@pytest.mark.asyncio
async def test_loopback_http_redirect_is_allowed() -> None:
    provider = YandexMcpOAuthProvider(
        store=InMemoryTokenStore((b"k" * 32,)),
        issuer_url="http://localhost:8000",
        resource_server_url="http://localhost:8000",
        yandex_client_id="yandex-client",
        yandex_callback_url="http://localhost:8000/oauth/yandex/callback",
        valid_scopes=["workspace:read", "workspace:write"],
    )
    client = _client(redirect_uris=["http://127.0.0.1:49152/callback"])
    await provider.register_client(client)
    assert await provider.get_client("client-id") is not None


@pytest.mark.asyncio
async def test_client_redirect_preserves_registered_query_parameters() -> None:
    store = InMemoryTokenStore((b"k" * 32,), clock=lambda: 100.0)
    provider = YandexMcpOAuthProvider(
        store=store,
        issuer_url="https://mcp.example",
        resource_server_url="https://mcp.example",
        yandex_client_id="yandex-client",
        yandex_callback_url="https://mcp.example/oauth/yandex/callback",
        valid_scopes=["workspace:read"],
        clock=lambda: 100.0,
    )
    client = _client(
        redirect_uris=["https://client.example/callback?tenant=a"],
        scope="workspace:read",
    )
    await provider.register_client(client)
    verifier = "v" * 48
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    upstream = await provider.authorize(
        client,
        AuthorizationParams(
            state="client-state",
            scopes=["workspace:read"],
            code_challenge=challenge,
            redirect_uri=AnyUrl("https://client.example/callback?tenant=a"),
            redirect_uri_provided_explicitly=True,
            resource="https://mcp.example",
        ),
    )
    redirect = await provider.complete_authorization(
        parse_qs(urlsplit(upstream).query)["state"][0], "subject"
    )

    assert parse_qs(urlsplit(redirect).query)["tenant"] == ["a"]
    assert parse_qs(urlsplit(redirect).query)["state"] == ["client-state"]

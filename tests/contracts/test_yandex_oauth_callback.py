from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from mcp.server.auth.provider import AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl
from starlette.requests import Request

from yandex_workspace_mcp.auth.oauth import YandexMcpOAuthProvider, YandexOAuthCallback
from yandex_workspace_mcp.auth.stores import InMemoryTokenStore, TokenStoreMiss


def _request(query: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/oauth/yandex/callback",
            "query_string": query.encode(),
            "headers": [],
            "scheme": "https",
            "server": ("mcp.example", 443),
            "client": ("203.0.113.10", 4444),
        }
    )


@pytest.mark.asyncio
async def test_callback_exchanges_code_resolves_subject_and_stores_downstream_token() -> None:
    now = [100.0]
    store = InMemoryTokenStore((b"k" * 32,), clock=lambda: now[0])
    provider = YandexMcpOAuthProvider(
        store=store,
        issuer_url="https://mcp.example",
        resource_server_url="https://mcp.example",
        yandex_client_id="yandex-client",
        yandex_callback_url="https://mcp.example/oauth/yandex/callback",
        valid_scopes=["workspace:read"],
        clock=lambda: now[0],
    )
    client = OAuthClientInformationFull(
        client_id="mcp-client",
        client_secret="mcp-client-secret",
        redirect_uris=[AnyUrl("https://client.example/callback")],
        scope="workspace:read",
    )
    await provider.register_client(client)
    authorize_url = await provider.authorize(
        client,
        AuthorizationParams(
            state="client-state",
            scopes=["workspace:read"],
            code_challenge="mcp-challenge",
            redirect_uri=AnyUrl("https://client.example/callback"),
            redirect_uri_provided_explicitly=True,
            resource="https://mcp.example",
        ),
    )
    state = parse_qs(urlsplit(authorize_url).query)["state"][0]

    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "oauth.yandex.ru":
            return httpx.Response(
                200,
                json={
                    "access_token": "yandex-access-secret",
                    "refresh_token": "yandex-refresh-secret",
                    "expires_in": 3600,
                },
            )
        return httpx.Response(200, json={"id": "yandex-subject", "login": "user"})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    callback = YandexOAuthCallback(
        provider=provider,
        store=store,
        yandex_client_id="yandex-client",
        yandex_client_secret="yandex-client-secret",
        callback_url="https://mcp.example/oauth/yandex/callback",
        organization_id="pinned-org",
        cloud_organization=False,
        client=http_client,
        clock=lambda: now[0],
    )
    response = await callback.handle(_request(f"code=upstream-code&state={state}"))
    assert response.status_code == 307
    location = response.headers["location"]
    assert location.startswith("https://client.example/callback?")
    assert parse_qs(urlsplit(location).query)["state"] == ["client-state"]

    principal = provider.principal_id("mcp-client", "yandex-subject")
    downstream = await store.get_downstream(principal)
    assert downstream.access_token == "yandex-access-secret"
    assert downstream.refresh_token == "yandex-refresh-secret"
    assert downstream.organization_id == "pinned-org"
    assert "yandex-access-secret" not in repr(store._records)
    assert requests[1].headers["Authorization"] == "OAuth yandex-access-secret"
    assert b"yandex-client-secret" in requests[0].content
    await http_client.aclose()


@pytest.mark.asyncio
async def test_callback_state_is_single_use_and_errors_are_generic() -> None:
    store = InMemoryTokenStore((b"k" * 32,))
    provider = YandexMcpOAuthProvider(
        store=store,
        issuer_url="https://mcp.example",
        resource_server_url="https://mcp.example",
        yandex_client_id="yc",
        yandex_callback_url="https://mcp.example/oauth/yandex/callback",
        valid_scopes=["workspace:read"],
    )
    callback = YandexOAuthCallback(
        provider=provider,
        store=store,
        yandex_client_id="yc",
        yandex_client_secret="secret",
        callback_url="https://mcp.example/oauth/yandex/callback",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _request: httpx.Response(500))
        ),
    )
    response = await callback.handle(_request("code=secret-code&state=unknown-state"))
    assert response.status_code == 400
    assert b"secret-code" not in response.body
    assert b"unknown-state" not in response.body
    with pytest.raises(TokenStoreMiss):
        await store.get_downstream("unknown")
    await callback.close()

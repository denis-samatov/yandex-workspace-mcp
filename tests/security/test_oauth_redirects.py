from urllib.parse import parse_qs, urlsplit

import pytest
from mcp.server.auth.provider import AuthorizationParams, AuthorizeError
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl

from yandex_workspace_mcp.auth.oauth import YandexMcpOAuthProvider
from yandex_workspace_mcp.auth.stores import InMemoryTokenStore


@pytest.mark.asyncio
async def test_callback_redirect_is_exact_registered_uri_and_state_cannot_replay() -> None:
    store = InMemoryTokenStore((b"k" * 32,))
    provider = YandexMcpOAuthProvider(
        store=store,
        issuer_url="https://mcp.example",
        resource_server_url="https://mcp.example",
        yandex_client_id="yc",
        yandex_callback_url="https://mcp.example/oauth/yandex/callback",
        valid_scopes=["workspace:read"],
    )
    client = OAuthClientInformationFull(
        client_id="client",
        redirect_uris=[AnyUrl("https://client.example/exact")],
        scope="workspace:read",
        token_endpoint_auth_method="none",
    )
    await provider.register_client(client)
    url = await provider.authorize(
        client,
        AuthorizationParams(
            state="client-state",
            scopes=["workspace:read"],
            code_challenge="challenge",
            redirect_uri=AnyUrl("https://client.example/exact"),
            redirect_uri_provided_explicitly=True,
            resource="https://mcp.example",
        ),
    )
    state = parse_qs(urlsplit(url).query)["state"][0]
    completed = await provider.complete_authorization(state, "subject")
    assert urlsplit(completed)._replace(query="").geturl() == "https://client.example/exact"
    with pytest.raises(AuthorizeError):
        await provider.complete_authorization(state, "subject")

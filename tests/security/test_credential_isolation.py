import asyncio

import httpx
import pytest
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from pydantic import SecretStr

from yandex_workspace_mcp.auth.credentials import (
    StaticCredentialProvider,
    YandexIAMCredential,
    YandexOAuthCredential,
)
from yandex_workspace_mcp.auth.models import DownstreamCredentialRecord
from yandex_workspace_mcp.auth.scopes import WorkspacePrincipal, WorkspaceScope
from yandex_workspace_mcp.clients.base import BaseYandexClient
from yandex_workspace_mcp.config import Settings
from yandex_workspace_mcp.server import create_application


def _principal(value: str) -> WorkspacePrincipal:
    return WorkspacePrincipal(value, frozenset({WorkspaceScope.READ}))


@pytest.mark.asyncio
async def test_oauth_and_iam_headers_are_immutable_and_deployment_selected() -> None:
    oauth = YandexOAuthCredential("oauth-secret", organization_id="org", cloud_organization=False)
    iam = YandexIAMCredential("iam-secret", organization_id="cloud-org")

    assert dict(oauth.request_credentials().headers) == {"X-Org-Id": "org"}
    assert oauth.request_credentials().authorization == "OAuth oauth-secret"
    assert dict(iam.request_credentials().headers) == {"X-Cloud-Org-Id": "cloud-org"}
    assert iam.request_credentials().authorization == "Bearer iam-secret"


@pytest.mark.asyncio
async def test_concurrent_request_credential_providers_do_not_share_tokens() -> None:
    gate = asyncio.Event()
    seen: list[tuple[str, str]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/a"):
            gate.set()
            await asyncio.sleep(0)
        else:
            await gate.wait()
        seen.append((request.url.path, request.headers["Authorization"]))
        return httpx.Response(200, json={"ok": True})

    current = {"principal": _principal("a")}
    credentials = {
        "a": YandexOAuthCredential("token-a"),
        "b": YandexOAuthCredential("token-b"),
    }

    async def resolve():
        principal = current["principal"]
        await asyncio.sleep(0)
        return credentials[principal.principal_id].request_credentials()

    client = BaseYandexClient(
        base_url="https://example.test",
        client=httpx.AsyncClient(
            base_url="https://example.test", transport=httpx.MockTransport(handler)
        ),
        credential_provider=resolve,
    )

    async def call(principal_id: str) -> None:
        # Each task captures its resolver in production; this test forces the same client path.
        provider = StaticCredentialProvider(credentials[principal_id])
        await client._request(
            "GET",
            f"/{principal_id}",
            credentials=(await provider.resolve(_principal(principal_id))).request_credentials(),
        )

    await asyncio.gather(call("a"), call("b"))
    assert sorted(seen) == [("/a", "OAuth token-a"), ("/b", "OAuth token-b")]
    await client.close()


@pytest.mark.asyncio
async def test_application_resolves_concurrent_principals_from_shared_store_without_leakage() -> (
    None
):
    application = create_application(
        Settings(
            mcp_transport="streamable-http",
            mcp_auth_mode="multi-user",
            yandex_auth_mode="multi-user",
            yandex_oauth_client_id="yandex-client",
            yandex_oauth_client_secret=SecretStr("yandex-secret"),
            mcp_oauth_callback_url="http://localhost:8000/oauth/yandex/callback",
            yandex_disk_enabled=False,
            yandex_wiki_enabled=False,
        )
    )
    assert application.auth_store is not None
    async with application.lifespan():
        for principal, token in (("principal-a", "token-a"), ("principal-b", "token-b")):
            await application.auth_store.put_downstream(
                principal,
                DownstreamCredentialRecord(
                    principal_id=principal,
                    access_token=token,
                    expires_at=4_000_000_000,
                    access_expires_at=4_000_000_000,
                ),
            )

        async def resolve(principal: str) -> str:
            context = auth_context_var.set(
                AuthenticatedUser(
                    AccessToken(
                        token=f"mcp-{principal}",
                        client_id="client",
                        subject=principal,
                        scopes=["workspace:read"],
                    )
                )
            )
            try:
                await asyncio.sleep(0)
                credentials = await application._request_credentials(include_organization=False)
                return credentials.authorization
            finally:
                auth_context_var.reset(context)

        assert await asyncio.gather(resolve("principal-a"), resolve("principal-b")) == [
            "OAuth token-a",
            "OAuth token-b",
        ]

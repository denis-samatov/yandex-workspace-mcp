import httpx
import pytest
from starlette.responses import JSONResponse

from yandex_workspace_mcp.config import McpAuthMode, Settings
from yandex_workspace_mcp.models.errors import ConfigurationError
from yandex_workspace_mcp.security.transport import TrustedProxyHeadersMiddleware
from yandex_workspace_mcp.server import create_application, create_http_app


@pytest.mark.asyncio
async def test_mcp_transport_rejects_invalid_host_origin_and_missing_bearer() -> None:
    application = create_application(
        Settings(
            mcp_transport="streamable-http",
            mcp_auth_mode="static",
            mcp_auth_token="mcp-secret",
            mcp_allowed_hosts=["mcp.example"],
            mcp_allowed_origins=["https://app.example"],
            yandex_disk_enabled=False,
            yandex_wiki_enabled=False,
        )
    )
    app = create_http_app(application)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),  # type: ignore[attr-defined]
        httpx.AsyncClient(transport=transport, base_url="http://mcp.example") as client,
    ):
        bad_host = await client.post(
            "/mcp",
            headers={
                "Host": "evil.example",
                "Content-Type": "application/json",
                "Authorization": "Bearer mcp-secret",
            },
            json={},
        )
        assert bad_host.status_code == 421

        bad_origin = await client.post(
            "/mcp",
            headers={
                "Host": "mcp.example",
                "Origin": "https://evil.example",
                "Content-Type": "application/json",
                "Authorization": "Bearer mcp-secret",
            },
            json={},
        )
        assert bad_origin.status_code == 403

        missing_bearer = await client.post(
            "/mcp",
            headers={
                "Host": "mcp.example",
                "Origin": "https://app.example",
                "Content-Type": "application/json",
            },
            json={},
        )
        assert missing_bearer.status_code == 401
        assert "resource_metadata" in missing_bearer.headers["www-authenticate"]


def test_http_app_rejects_application_validated_for_stdio() -> None:
    application = create_application(
        Settings(
            mcp_transport="stdio",
            mcp_host="0.0.0.0",
            yandex_disk_enabled=False,
            yandex_wiki_enabled=False,
        )
    )

    with pytest.raises(ConfigurationError):
        create_http_app(application)


def test_http_app_rejects_settings_mutated_after_server_construction() -> None:
    application = create_application(
        Settings(
            mcp_transport="streamable-http",
            mcp_auth_mode="static",
            mcp_auth_token="mcp-secret",
            yandex_disk_enabled=False,
            yandex_wiki_enabled=False,
        )
    )
    object.__setattr__(application.settings, "mcp_auth_mode", McpAuthMode.LOCAL)

    with pytest.raises(ConfigurationError):
        create_http_app(application)


@pytest.mark.asyncio
async def test_forwarded_headers_are_used_only_for_a_trusted_direct_peer() -> None:
    async def echo(scope, _receive, send):
        host = dict(scope["headers"])[b"host"].decode()
        await JSONResponse({"scheme": scope["scheme"], "host": host})(scope, _receive, send)

    app = TrustedProxyHeadersMiddleware(echo, ["10.0.0.0/8"])

    trusted = httpx.ASGITransport(app=app, client=("10.1.2.3", 1234))
    async with httpx.AsyncClient(transport=trusted, base_url="http://internal") as client:
        response = await client.get(
            "/", headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "mcp.example"}
        )
        assert response.json() == {"scheme": "https", "host": "mcp.example"}

    untrusted = httpx.ASGITransport(app=app, client=("203.0.113.8", 1234))
    async with httpx.AsyncClient(transport=untrusted, base_url="http://internal") as client:
        response = await client.get(
            "/", headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "mcp.example"}
        )
        assert response.json() == {"scheme": "http", "host": "internal"}

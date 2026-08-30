import httpx
import pytest

from yandex_workspace_mcp.config import Settings
from yandex_workspace_mcp.server import create_application, create_http_app


@pytest.mark.asyncio
async def test_health_is_credential_free_and_contains_no_configuration() -> None:
    application = create_application(
        Settings(
            mcp_transport="streamable-http",
            mcp_auth_mode="static",
            mcp_auth_token="mcp-secret",
            yandex_disk_enabled=False,
            yandex_wiki_enabled=False,
        )
    )
    transport = httpx.ASGITransport(app=create_http_app(application))
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost:8000") as client:
        response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["cache-control"] == "no-store"

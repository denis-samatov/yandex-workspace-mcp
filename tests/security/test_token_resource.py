import pytest
from mcp.server.auth.middleware.bearer_auth import BearerAuthBackend
from pydantic import AnyHttpUrl
from starlette.requests import HTTPConnection

from yandex_workspace_mcp.config import Settings
from yandex_workspace_mcp.server import StaticTokenVerifier, create_application


def test_http_server_enables_resource_validation() -> None:
    app = create_application(
        Settings(
            mcp_transport="streamable-http",
            mcp_auth_mode="static",
            mcp_auth_token="test-token",
            yandex_disk_enabled=False,
            yandex_wiki_enabled=False,
        )
    )
    assert app.mcp_server.settings.auth is not None
    assert app.mcp_server.settings.auth.validate_token_resource is True


@pytest.mark.asyncio
async def test_verifier_resource_is_enforced_by_sdk() -> None:
    expected = "https://mcp.example/mcp"
    connection = HTTPConnection(
        {"type": "http", "headers": [(b"authorization", b"Bearer test-token")]}
    )
    for resource, accepted in [(expected, True), ("https://other.example/mcp", False)]:
        verifier = StaticTokenVerifier("test-token", resource=resource)
        backend = BearerAuthBackend(verifier, resource_server_url=AnyHttpUrl(expected))
        result = await backend.authenticate(connection)
        assert (result is not None) is accepted

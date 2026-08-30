import base64

import pytest
from pydantic import SecretStr, ValidationError

from yandex_workspace_mcp.config import AuthStoreBackend, McpAuthMode, Settings, YandexAuthMode


def _key(byte: bytes = b"k") -> SecretStr:
    return SecretStr(base64.urlsafe_b64encode(byte * 32).rstrip(b"=").decode())


def test_static_oauth_and_iam_modes_are_mutually_exclusive() -> None:
    oauth = Settings(yandex_oauth_token=SecretStr("oauth"))
    assert oauth.yandex_auth_mode is YandexAuthMode.OAUTH

    iam = Settings(
        yandex_auth_mode="iam",
        yandex_iam_token=SecretStr("iam"),
        yandex_iam_org_id="org-id",
    )
    assert iam.yandex_auth_mode is YandexAuthMode.IAM

    with pytest.raises(ValidationError, match="organization"):
        Settings(yandex_auth_mode="iam", yandex_iam_token=SecretStr("iam"))
    with pytest.raises(ValidationError, match="mutually exclusive"):
        Settings(
            yandex_auth_mode="iam",
            yandex_iam_token=SecretStr("iam"),
            yandex_iam_org_id="org-id",
            yandex_oauth_token=SecretStr("oauth"),
        )


def test_non_loopback_http_requires_auth_https_and_explicit_network_policy() -> None:
    with pytest.raises(ValidationError, match="authentication"):
        Settings(mcp_transport="streamable-http", mcp_host="0.0.0.0")

    base = {
        "mcp_transport": "streamable-http",
        "mcp_host": "0.0.0.0",
        "mcp_auth_mode": "static",
        "mcp_auth_token": "mcp-secret",
        "mcp_allowed_hosts": ["mcp.example.test"],
        "mcp_allowed_origins": ["https://app.example.test"],
        "mcp_cursor_keys": [_key()],
    }
    with pytest.raises(ValidationError, match="HTTPS"):
        Settings(**base)

    settings = Settings(
        **base,
        mcp_issuer_url="https://mcp.example.test",
        mcp_resource_server_url="https://mcp.example.test",
    )
    assert settings.mcp_auth_mode is McpAuthMode.STATIC


def test_loopback_http_remains_available_for_local_development() -> None:
    settings = Settings(
        mcp_transport="streamable-http",
        mcp_host="127.0.0.1",
        mcp_issuer_url="http://localhost:8000",
        mcp_resource_server_url="http://localhost:8000",
    )
    assert settings.mcp_auth_mode is McpAuthMode.LOCAL


def test_multi_user_production_requires_redis_encryption_and_callback() -> None:
    base = {
        "mcp_transport": "streamable-http",
        "mcp_host": "0.0.0.0",
        "mcp_auth_mode": "multi-user",
        "yandex_auth_mode": "multi-user",
        "mcp_issuer_url": "https://mcp.example.test",
        "mcp_resource_server_url": "https://mcp.example.test",
        "mcp_oauth_callback_url": "https://mcp.example.test/oauth/yandex/callback",
        "mcp_allowed_hosts": ["mcp.example.test"],
        "mcp_allowed_origins": ["https://app.example.test"],
        "mcp_cursor_keys": [_key(b"c")],
        "yandex_oauth_client_id": "client-id",
        "yandex_oauth_client_secret": SecretStr("client-secret"),
    }
    with pytest.raises(ValidationError, match="Redis"):
        Settings(**base)

    settings = Settings(
        **base,
        auth_store_backend="redis",
        redis_url=SecretStr("redis://redis.internal:6379/0"),
        mcp_token_encryption_keys=[_key(b"e")],
    )
    assert settings.auth_store_backend is AuthStoreBackend.REDIS


@pytest.mark.parametrize(
    "field,value",
    [
        ("mcp_allowed_hosts", ["*"]),
        ("mcp_allowed_origins", ["*"]),
        ("mcp_trusted_proxy_cidrs", ["not-a-network"]),
    ],
)
def test_network_policy_rejects_wildcards_and_invalid_cidrs(field: str, value: list[str]) -> None:
    with pytest.raises(ValidationError):
        Settings(**{field: value})


def test_misspelled_project_prefixed_environment_key_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("MCP_AUT_TOKEN", "typo")
    with pytest.raises(ValidationError, match="MCP_AUT_TOKEN"):
        Settings()


def test_mcp_bearer_is_secret_distinct_from_upstream_and_multi_user_is_http_only() -> None:
    with pytest.raises(ValidationError, match="distinct"):
        Settings(
            mcp_auth_mode="static",
            mcp_auth_token="same-secret",
            yandex_oauth_token=SecretStr("same-secret"),
        )
    with pytest.raises(ValidationError, match="Streamable HTTP"):
        Settings(
            mcp_auth_mode="multi-user",
            yandex_auth_mode="multi-user",
            yandex_oauth_client_id="client",
            yandex_oauth_client_secret=SecretStr("secret"),
            mcp_oauth_callback_url="http://localhost:8000/oauth/yandex/callback",
        )

    settings = Settings(mcp_auth_mode="static", mcp_auth_token="mcp-only")
    assert settings.mcp_auth_token is not None
    assert "mcp-only" not in repr(settings.mcp_auth_token)

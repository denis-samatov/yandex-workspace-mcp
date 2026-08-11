from typing import Any

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Transports
    mcp_transport: str = Field(default="stdio", description="MCP transport to use: 'stdio' or 'streamable-http'")
    mcp_host: str = Field(default="127.0.0.1", description="HTTP host for Streamable HTTP")
    mcp_port: int = Field(default=8000, alias="MCP_PORT")
    mcp_auth_token: str | None = Field(default=None, alias="MCP_AUTH_TOKEN")
    
    # Yandex Workspace Config
    yandex_disk_enabled: bool = Field(default=True)
    yandex_wiki_enabled: bool = Field(default=True)

    yandex_oauth_token: SecretStr | None = Field(default=None, description="Global Yandex OAuth Token for local execution mode")
    yandex_wiki_org_id: str | None = Field(default=None, description="Yandex Wiki Organization ID (X-Org-Id or X-Cloud-Org-Id)")
    yandex_wiki_is_cloud_org: bool = Field(default=False, description="Set to True if using Yandex Cloud Organization")

    # Permissions
    disk_read: bool = Field(default=True)
    disk_write: bool = Field(default=False)
    disk_delete: bool = Field(default=False)
    
    wiki_read: bool = Field(default=True)
    wiki_write: bool = Field(default=False)
    wiki_delete: bool = Field(default=False)

    # Allowed Roots
    disk_allowed_roots: list[str] = Field(default_factory=list)
    wiki_allowed_roots: list[str] = Field(default_factory=list)

    # Limits
    max_search_results: int = Field(default=50)
    max_upload_size_mb: int = Field(default=100)
    max_download_size_mb: int = Field(default=100)
    max_inline_text_size_kb: int = Field(default=512)

    @field_validator("disk_allowed_roots", "wiki_allowed_roots", mode="before")
    @classmethod
    def parse_roots(cls, val: Any) -> list[str]:
        if isinstance(val, str):
            # Parse from comma separated string
            return [x.strip() for x in val.split(",") if x.strip()]
        if isinstance(val, list):
            return val
        return []



def get_settings() -> Settings:
    return Settings()

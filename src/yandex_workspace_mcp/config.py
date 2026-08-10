from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr
from typing import List, Optional
import os


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Transports
    mcp_transport: str = Field(default="stdio", description="MCP transport to use: 'stdio' or 'streamable-http'")
    mcp_host: str = Field(default="127.0.0.1", description="HTTP host for Streamable HTTP")
    mcp_port: int = Field(default=8000, description="HTTP port for Streamable HTTP")
    
    # Yandex Workspace Config
    yandex_disk_enabled: bool = Field(default=True)
    yandex_wiki_enabled: bool = Field(default=True)

    yandex_oauth_token: Optional[SecretStr] = Field(default=None, description="Global Yandex OAuth Token for local execution mode")
    yandex_wiki_org_id: Optional[str] = Field(default=None, description="Yandex Wiki Organization ID (X-Org-Id or X-Cloud-Org-Id)")
    yandex_wiki_is_cloud_org: bool = Field(default=False, description="Set to True if using Yandex Cloud Organization")

    # Permissions
    disk_read: bool = Field(default=True)
    disk_write: bool = Field(default=False)
    disk_delete: bool = Field(default=False)
    
    wiki_read: bool = Field(default=True)
    wiki_write: bool = Field(default=False)
    wiki_delete: bool = Field(default=False)

    # Allowed Roots
    disk_allowed_roots: List[str] = Field(default=["/"])
    wiki_allowed_roots: List[str] = Field(default=["/"])

    # Limits
    max_search_results: int = Field(default=50)
    max_upload_size_mb: int = Field(default=100)
    max_download_size_mb: int = Field(default=100)
    max_inline_text_size_kb: int = Field(default=512)

    def parse_list(self, val: str | List[str]) -> List[str]:
        if isinstance(val, str):
            return [x.strip() for x in val.split(",") if x.strip()]
        return val


def get_settings() -> Settings:
    return Settings()

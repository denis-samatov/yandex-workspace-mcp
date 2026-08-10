from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class DiskSettings(BaseSettings):
    enabled: bool = Field(default=True, validation_alias="YANDEX_DISK_ENABLED")
    read: bool = Field(default=True, validation_alias="DISK_READ")
    write: bool = Field(default=False, validation_alias="DISK_WRITE")
    delete: bool = Field(default=False, validation_alias="DISK_DELETE")
    allowed_roots: list[str] = Field(default_factory=list, validation_alias="DISK_ALLOWED_ROOTS")

class WikiSettings(BaseSettings):
    enabled: bool = Field(default=True, validation_alias="YANDEX_WIKI_ENABLED")
    org_id: str | None = Field(default=None, validation_alias="YANDEX_WIKI_ORG_ID")
    read: bool = Field(default=True, validation_alias="WIKI_READ")
    write: bool = Field(default=False, validation_alias="WIKI_WRITE")
    delete: bool = Field(default=False, validation_alias="WIKI_DELETE")
    allowed_roots: list[str] = Field(default_factory=list, validation_alias="WIKI_ALLOWED_ROOTS")

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_parse_none_str="None"
    )

    oauth_token: str = Field(..., validation_alias="YANDEX_OAUTH_TOKEN")
    transport: str = Field(default="stdio", validation_alias="MCP_TRANSPORT")
    
    disk: DiskSettings = Field(default_factory=DiskSettings)
    wiki: WikiSettings = Field(default_factory=WikiSettings)

    def validate_setup(self) -> None:
        if self.wiki.enabled and not self.wiki.org_id:
            raise ValueError("YANDEX_WIKI_ORG_ID is required when Yandex Wiki is enabled")

def get_settings() -> Settings:
    settings = Settings()
    settings.validate_setup()
    return settings

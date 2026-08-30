from pydantic import BaseModel, ConfigDict


class PublicModel(BaseModel):
    """Stable MCP-facing contract."""

    model_config = ConfigDict(extra="forbid", strict=True)


class WireModel(BaseModel):
    """Upstream contract that tolerates additive Yandex fields."""

    model_config = ConfigDict(extra="allow")

from typing import Literal

from pydantic import BaseModel, Field


class ResourceRef(BaseModel):
    id: str
    source: Literal["disk", "wiki"]
    title: str
    url: str | None = None
    type: str = "unknown"
    modified_at: str | None = None
    locator: str | None = None


class SearchResult(BaseModel):
    results: list[ResourceRef]
    next_cursor: str | None = None
    partial_failures: dict[str, str] = Field(default_factory=dict)
    sources: dict[str, "SourceStatus"] = Field(default_factory=dict)


class SourceStatus(BaseModel):
    state: Literal["success", "degraded", "failure"]
    search_mode: str | None = None
    error_category: str | None = None


class FetchResult(BaseModel):
    id: str
    title: str
    text: str | None = None
    url: str | None = None
    metadata: dict


SearchResult.model_rebuild()

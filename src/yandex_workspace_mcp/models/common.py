from pydantic import BaseModel, ConfigDict
from typing import Optional, Literal

class ResourceRef(BaseModel):
    id: str
    source: Literal["disk", "wiki"]
    title: str
    url: Optional[str] = None
    type: str = "unknown"
    modified_at: Optional[str] = None
    locator: Optional[str] = None

class SearchResult(BaseModel):
    results: list[ResourceRef]
    next_cursor: Optional[str] = None

class FetchResult(BaseModel):
    id: str
    title: str
    text: Optional[str] = None
    url: Optional[str] = None
    metadata: dict

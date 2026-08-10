from pydantic import Field
from yandex_workspace_mcp.models.common import BaseResource
from typing import Literal

class WorkspaceSearchResultItem(BaseResource):
    source: Literal["disk", "wiki"]
    type: Literal["file", "dir", "page"]
    title: str
    locator: str # path or slug
    stable_id: str | None = None
    url: str | None = None
    modified_at: str | None = None

class WorkspaceSearchResult(BaseResource):
    query: str
    results: list[WorkspaceSearchResultItem]

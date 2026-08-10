from datetime import datetime
from pydantic import Field
from yandex_workspace_mcp.models.common import BaseResource
from typing import Any

class WikiUser(BaseResource):
    login: str | None = None
    name: str | None = None
    uid: str | None = None

class WikiPage(BaseResource):
    id: str | None = None
    title: str
    slug: str
    content: str | None = None
    url: str | None = None
    created_at: datetime | str | None = Field(None, alias="createdAt")
    modified_at: datetime | str | None = Field(None, alias="modifiedAt")
    version: str | int | None = None # Used for optimistic locking
    author: WikiUser | None = Field(None, alias="authors") # Sometime Wiki uses authors array
    modified_by: WikiUser | None = Field(None, alias="lastEditor")
    
class WikiSearchResult(BaseResource):
    items: list[WikiPage]

class WikiAttachment(BaseResource):
    id: str | None = None
    name: str
    content_type: str | None = None
    size: int | None = None
    created_at: datetime | str | None = Field(None, alias="createdAt")
    url: str | None = None

class WikiComment(BaseResource):
    id: str | int | None = None
    text: str | None = None
    created_at: datetime | str | None = Field(None, alias="createdAt")
    author: WikiUser | None = Field(None, alias="author")

class WikiTable(BaseResource):
    id: str | None = None
    title: str | None = None
    rows: list[dict] | None = None

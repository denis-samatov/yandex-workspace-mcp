from datetime import datetime
from pydantic import Field
from yandex_workspace_mcp.models.common import BaseResource
from typing import Literal

class DiskItem(BaseResource):
    name: str
    path: str
    type: Literal["dir", "file"]
    size: int | None = None
    modified_at: datetime | str | None = Field(None, alias="modified")
    created_at: datetime | str | None = Field(None, alias="created")
    mime_type: str | None = None

class DiskListResult(BaseResource):
    path: str
    items: list[DiskItem]

class DiskLink(BaseResource):
    href: str
    method: str

from typing import Any
from yandex_workspace_mcp.clients.base import BaseClient
from yandex_workspace_mcp.models.disk import DiskListResult, DiskItem, DiskLink
import urllib.parse
from datetime import datetime

class YandexDiskClient(BaseClient):
    """Client for Yandex Disk REST API."""

    def __init__(self, auth_flow: Any):
        super().__init__(auth_flow=auth_flow, base_url="https://cloud-api.yandex.net/v1/disk/")

    async def get_metadata(self, path: str, limit: int = 100, offset: int = 0) -> dict:
        """Get metadata for a file or folder."""
        params = {
            "path": path,
            "limit": limit,
            "offset": offset
        }
        response = await self.get("resources", params=params)
        return response.json()

    async def list_folder(self, path: str, limit: int = 100, offset: int = 0) -> DiskListResult:
        """List contents of a folder."""
        data = await self.get_metadata(path, limit=limit, offset=offset)
        
        items = []
        if "_embedded" in data and "items" in data["_embedded"]:
            for item in data["_embedded"]["items"]:
                path = item.get("path", "")
                if path.startswith("disk:/"):
                    path = path[5:]
                items.append(
                    DiskItem(
                        name=item.get("name", ""),
                        path=path,
                        type=item.get("type", "file"),
                        size=item.get("size"),
                        modified=item.get("modified"),
                        created=item.get("created"),
                        mime_type=item.get("mime_type")
                    )
                )
                
        return DiskListResult(path=path, items=items)
        
    async def get_download_link(self, path: str) -> DiskLink:
        """Get download link for a file."""
        response = await self.get("resources/download", params={"path": path})
        return DiskLink.model_validate(response.json())

    async def get_upload_link(self, path: str, overwrite: bool = False) -> DiskLink:
        """Get upload link for a file."""
        response = await self.get("resources/upload", params={"path": path, "overwrite": overwrite})
        return DiskLink.model_validate(response.json())
        
    async def create_folder(self, path: str) -> DiskLink:
        """Create a new folder."""
        response = await self.put("resources", params={"path": path})
        return DiskLink.model_validate(response.json())
        
    async def delete(self, path: str, permanently: bool = False) -> None:
        """Delete a file or folder."""
        await super().delete("resources", params={"path": path, "permanently": permanently})
        
    async def move(self, from_path: str, to_path: str, overwrite: bool = False) -> DiskLink:
        """Move a file or folder."""
        response = await self.post("resources/move", params={"from": from_path, "path": to_path, "overwrite": overwrite})
        return DiskLink.model_validate(response.json())

    async def copy(self, from_path: str, to_path: str, overwrite: bool = False) -> DiskLink:
        """Copy a file or folder."""
        response = await self.post("resources/copy", params={"from": from_path, "path": to_path, "overwrite": overwrite})
        return DiskLink.model_validate(response.json())

    async def get_flat_files(self, limit: int = 100, offset: int = 0) -> list[DiskItem]:
        """Get a flat list of all files on the Disk (useful for fallback search)."""
        response = await self.get("resources/files", params={"limit": limit, "offset": offset})
        data = response.json()
        items = []
        for item in data.get("items", []):
            path = item.get("path", "")
            if path.startswith("disk:/"):
                path = path[5:]
            items.append(
                DiskItem(
                    name=item.get("name", ""),
                    path=path,
                    type=item.get("type", "file"),
                    size=item.get("size"),
                    modified=item.get("modified"),
                    created=item.get("created"),
                    mime_type=item.get("mime_type")
                )
            )
        return items

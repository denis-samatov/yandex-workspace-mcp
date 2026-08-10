from typing import Any
from httpx import AsyncClient
from yandex_workspace_mcp.clients.disk import YandexDiskClient
from yandex_workspace_mcp.models.disk import DiskListResult, DiskItem
from yandex_workspace_mcp.security.permissions import check_disk_read, check_disk_write, check_disk_delete
from yandex_workspace_mcp.security.audit import log_audit_event
from yandex_workspace_mcp.security.paths import normalize_path
from yandex_workspace_mcp.logging import get_logger

logger = get_logger(__name__)

class DiskService:
    def __init__(self, client: YandexDiskClient):
        self.client = client

    async def list_folder(self, path: str, limit: int = 100, offset: int = 0) -> DiskListResult:
        check_disk_read(path)
        norm_path = normalize_path(path)
        return await self.client.list_folder(norm_path, limit, offset)

    async def get_metadata(self, path: str) -> dict:
        check_disk_read(path)
        norm_path = normalize_path(path)
        return await self.client.get_metadata(norm_path)

    async def read_file(self, path: str) -> dict[str, str]:
        """Get file metadata and download URL. Doesn't download actual content to avoid large payloads."""
        check_disk_read(path)
        norm_path = normalize_path(path)
        
        # Get metadata first to check size and type
        meta = await self.client.get_metadata(norm_path)
        if meta.get("type") == "dir":
            raise ValueError(f"Cannot read a directory: {norm_path}")
            
        link = await self.client.get_download_link(norm_path)
        
        return {
            "name": meta.get("name", ""),
            "path": norm_path,
            "mime_type": meta.get("mime_type", ""),
            "size": meta.get("size", 0),
            "download_url": link.href
        }

    async def find_files(self, query: str, root: str = "/", limit: int = 20) -> list[DiskItem]:
        check_disk_read(root)
        norm_root = normalize_path(root)
        
        # We fetch files and filter them as Yandex Disk REST API doesn't have a direct search by name
        # We will get files and do simple client-side filtering.
        # To avoid pulling everything, we pull a chunk and filter.
        # This is a naive implementation, ideally WebDAV PROPFIND with SEARCH could be used if required.
        files = await self.client.get_flat_files(limit=1000)
        
        results = []
        for f in files:
            if not f.path.startswith(norm_root):
                continue
            if query.lower() in f.name.lower():
                results.append(f)
                if len(results) >= limit:
                    break
                    
        return results

    async def create_folder(self, path: str) -> None:
        check_disk_write(path)
        norm_path = normalize_path(path)
        await self.client.create_folder(norm_path)
        log_audit_event("disk", "create_folder", norm_path, "success")

    async def delete(self, path: str, permanently: bool = False) -> None:
        check_disk_delete(path)
        norm_path = normalize_path(path)
        await self.client.delete(norm_path, permanently)
        log_audit_event("disk", "delete", norm_path, "success", permanently=permanently)

    async def copy(self, from_path: str, to_path: str, overwrite: bool = False) -> None:
        check_disk_read(from_path)
        check_disk_write(to_path)
        norm_from = normalize_path(from_path)
        norm_to = normalize_path(to_path)
        
        await self.client.copy(norm_from, norm_to, overwrite)
        log_audit_event("disk", "copy", norm_to, "success", source=norm_from)

    async def move(self, from_path: str, to_path: str, overwrite: bool = False) -> None:
        check_disk_write(from_path) # Needs write permission to move (delete from source)
        check_disk_write(to_path)
        norm_from = normalize_path(from_path)
        norm_to = normalize_path(to_path)
        
        await self.client.move(norm_from, norm_to, overwrite)
        log_audit_event("disk", "move", norm_to, "success", source=norm_from)
        
    async def get_upload_link(self, path: str, overwrite: bool = False) -> str:
        """Returns the URL where a file can be uploaded via PUT."""
        check_disk_write(path)
        norm_path = normalize_path(path)
        link = await self.client.get_upload_link(norm_path, overwrite)
        return link.href

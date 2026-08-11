from typing import Any

import structlog

from ..clients.disk import YandexDiskClient
from ..models.errors import InvalidPath, PermissionDenied
from ..policies.paths import validate_path
from ..security.audit import audit_logger

logger = structlog.get_logger()

class DiskService:
    def __init__(self, client: YandexDiskClient, allowed_roots: list[str], can_read: bool, can_write: bool, can_delete: bool):
        self.client = client
        self.allowed_roots = allowed_roots
        self.can_read = can_read
        self.can_write = can_write
        self.can_delete = can_delete

    async def list_folder(self, path: str, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        if not self.can_read:
            raise PermissionDenied("Disk read is disabled.")
        valid_path = validate_path(path, self.allowed_roots)
        logger.info("disk.list", path=valid_path)
        return await self.client.get_metadata(valid_path, limit=limit, offset=offset)

    async def search(self, query: str, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        if not self.can_read:
            raise PermissionDenied("Disk read is disabled.")
        logger.info("disk.search", query=query)
        
        matched: list[dict[str, Any]] = []
        current_offset = offset
        batch_size = 100
        max_scans = 1000 # Prevent infinite loops
        scanned = 0
        query_lower = query.lower()

        while len(matched) < limit and scanned < max_scans:
            try:
                res = await self.client.flat_files(limit=batch_size, offset=current_offset)
                items = res.get("items", [])
                if not items:
                    break
                
                for item in items:
                    if query_lower in item.get("name", "").lower():
                        try:
                            item_path = item.get("path", "").replace("disk:", "")
                            validate_path(item_path, self.allowed_roots)
                            matched.append(item)
                            if len(matched) >= limit:
                                break
                        except InvalidPath:
                            pass
                
                current_offset += batch_size
                scanned += len(items)
            except Exception as e:  # noqa: BLE001
                logger.error("disk.search.error", error=str(e))
                break

        return {"items": matched}

    async def get_metadata(self, path: str) -> dict[str, Any]:
        if not self.can_read:
            raise PermissionDenied("Disk read is disabled.")
        valid_path = validate_path(path, self.allowed_roots)
        logger.info("disk.metadata", path=valid_path)
        return await self.client.get_metadata(valid_path, limit=1)

    async def read_file(self, path: str) -> str:
        if not self.can_read:
            raise PermissionDenied("Disk read is disabled.")
        valid_path = validate_path(path, self.allowed_roots)
        
        # Check MIME type
        meta = await self.client.get_metadata(valid_path, limit=1)
        mime = meta.get("mime_type", "")
        if mime and not mime.startswith("text/") and "json" not in mime and "xml" not in mime and mime != "application/x-empty":
            raise PermissionDenied(f"Cannot read binary file as text: {mime}")
            
        logger.info("disk.read", path=valid_path)
        return await self.client.read_file_text(valid_path)

    async def get_download_url(self, path: str) -> str:
        if not self.can_read:
            raise PermissionDenied("Disk read is disabled.")
        valid_path = validate_path(path, self.allowed_roots)
        return await self.client.get_download_url(valid_path)

    async def create_folder(self, path: str) -> dict[str, Any]:
        if not self.can_write:
            raise PermissionDenied("Disk write is disabled.")
        valid_path = validate_path(path, self.allowed_roots)
        logger.info("disk.create_folder", path=valid_path)
        audit_logger.log("disk.create_folder", path=valid_path)
        resp = await self.client._request("PUT", "/resources", params={"path": valid_path})
        resp.raise_for_status()
        return {"status": "created", "path": valid_path}

    async def copy(self, from_path: str, to_path: str) -> dict[str, Any]:
        if not self.can_write:
            raise PermissionDenied("Disk write is disabled.")
        valid_from = validate_path(from_path, self.allowed_roots)
        valid_to = validate_path(to_path, self.allowed_roots)
        logger.info("disk.copy", from_path=valid_from, to_path=valid_to)
        audit_logger.log("disk.copy", from_path=valid_from, to_path=valid_to)
        resp = await self.client._request("POST", "/resources/copy", params={"from": valid_from, "path": valid_to})
        resp.raise_for_status()
        return {"status": "copied", "from": valid_from, "to": valid_to}

    async def move(self, from_path: str, to_path: str) -> dict[str, Any]:
        if not self.can_write:
            raise PermissionDenied("Disk write is disabled.")
        valid_from = validate_path(from_path, self.allowed_roots)
        valid_to = validate_path(to_path, self.allowed_roots)
        logger.info("disk.move", from_path=valid_from, to_path=valid_to)
        audit_logger.log("disk.move", from_path=valid_from, to_path=valid_to)
        resp = await self.client._request("POST", "/resources/move", params={"from": valid_from, "path": valid_to})
        resp.raise_for_status()
        return {"status": "moved", "from": valid_from, "to": valid_to}

    async def delete(self, path: str, permanently: bool = False) -> dict[str, Any]:
        if not self.can_delete:
            raise PermissionDenied("Disk delete is disabled.")
        valid_path = validate_path(path, self.allowed_roots)
        logger.info("disk.delete", path=valid_path, permanently=permanently)
        audit_logger.log("disk.delete", path=valid_path, permanently=permanently)
        resp = await self.client._request("DELETE", "/resources", params={"path": valid_path, "permanently": str(permanently).lower()})
        resp.raise_for_status()
        return {"status": "deleted", "path": valid_path}

    async def upload(self, path: str, content: str) -> dict[str, Any]:
        if not self.can_write:
            raise PermissionDenied("Disk write is disabled.")
        valid_path = validate_path(path, self.allowed_roots)
        
        from ..config import get_settings
        settings = get_settings()
        max_bytes = settings.max_upload_size_mb * 1024 * 1024
        
        if len(content.encode("utf-8")) > max_bytes:
            raise PermissionDenied(f"Upload exceeds maximum size of {settings.max_upload_size_mb}MB")
            
        logger.info("disk.upload", path=valid_path)
        audit_logger.log("disk.upload", path=valid_path, size=len(content))
        # Use safe client logic
        await self.client.upload_file_text(valid_path, content)
        
        return {"status": "uploaded", "path": valid_path}

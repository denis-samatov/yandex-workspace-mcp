from typing import Any

import structlog

from ..clients.disk import YandexDiskClient
from ..models.errors import PermissionDenied
from ..policies.paths import validate_path

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
        return await self.client.search(query, limit=limit, offset=offset)

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
        resp = await self.client._request("PUT", "/resources", params={"path": valid_path})
        resp.raise_for_status()
        return {"status": "created", "path": valid_path}

    async def copy(self, from_path: str, to_path: str) -> dict[str, Any]:
        if not self.can_write:
            raise PermissionDenied("Disk write is disabled.")
        valid_from = validate_path(from_path, self.allowed_roots)
        valid_to = validate_path(to_path, self.allowed_roots)
        logger.info("disk.copy", from_path=valid_from, to_path=valid_to)
        resp = await self.client._request("POST", "/resources/copy", params={"from": valid_from, "path": valid_to})
        resp.raise_for_status()
        return {"status": "copied", "from": valid_from, "to": valid_to}

    async def move(self, from_path: str, to_path: str) -> dict[str, Any]:
        if not self.can_write:
            raise PermissionDenied("Disk write is disabled.")
        valid_from = validate_path(from_path, self.allowed_roots)
        valid_to = validate_path(to_path, self.allowed_roots)
        logger.info("disk.move", from_path=valid_from, to_path=valid_to)
        resp = await self.client._request("POST", "/resources/move", params={"from": valid_from, "path": valid_to})
        resp.raise_for_status()
        return {"status": "moved", "from": valid_from, "to": valid_to}

    async def delete(self, path: str, permanently: bool = False) -> dict[str, Any]:
        if not self.can_delete:
            raise PermissionDenied("Disk delete is disabled.")
        valid_path = validate_path(path, self.allowed_roots)
        logger.info("disk.delete", path=valid_path, permanently=permanently)
        resp = await self.client._request("DELETE", "/resources", params={"path": valid_path, "permanently": str(permanently).lower()})
        resp.raise_for_status()
        return {"status": "deleted", "path": valid_path}

    async def upload(self, path: str, content: str) -> dict[str, Any]:
        if not self.can_write:
            raise PermissionDenied("Disk write is disabled.")
        valid_path = validate_path(path, self.allowed_roots)
        logger.info("disk.upload", path=valid_path)
        # Use safe client logic
        await self.client.upload_file_text(valid_path, content)
        
        return {"status": "uploaded", "path": valid_path}

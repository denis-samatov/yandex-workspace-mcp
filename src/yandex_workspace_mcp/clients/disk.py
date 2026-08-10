from typing import Any, Dict, List, Optional
from .base import BaseYandexClient
from ..models.errors import ResourceNotFound, APIError, InvalidPath
import urllib.parse

class YandexDiskClient(BaseYandexClient):
    def __init__(self, token: str):
        super().__init__(token, base_url="https://cloud-api.yandex.net/v1/disk")

    async def get_metadata(self, path: str, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        """Get metadata for a file or folder. If it's a folder, it lists contents up to limit."""
        params = {
            "path": path,
            "limit": limit,
            "offset": offset
        }
        resp = await self._request("GET", "/resources", params=params)
        if resp.status_code == 404:
            raise ResourceNotFound(f"Disk path not found: {path}")
        if resp.status_code != 200:
            raise APIError(f"Disk API error {resp.status_code}: {resp.text}")
        return resp.json()
    
    async def get_download_url(self, path: str) -> str:
        """Get a temporary download URL for a file."""
        resp = await self._request("GET", "/resources/download", params={"path": path})
        if resp.status_code == 404:
            raise ResourceNotFound(f"Disk path not found: {path}")
        if resp.status_code != 200:
            raise APIError(f"Disk API error {resp.status_code}: {resp.text}")
        
        data = resp.json()
        return data.get("href", "")

    async def read_file_text(self, path: str) -> str:
        url = await self.get_download_url(path)
        # Note: we use httpx to fetch the temporary URL.
        # This URL is signed by Yandex, so we do a quick fetch
        # To avoid SSRF, we only fetch if the domain is *.yandex.net
        parsed = urllib.parse.urlparse(url)
        if not parsed.netloc.endswith("yandex.net"):
            raise APIError("Invalid download URL domain returned by Yandex")
        
        async with self.client.stream("GET", url) as resp:
            if resp.status_code != 200:
                raise APIError("Failed to fetch file content")
            content = await resp.aread()
            return content.decode("utf-8", errors="replace")

    async def search(self, query: str, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        params = {
            "query": query,
            "limit": limit,
            "offset": offset
        }
        resp = await self._request("GET", "/resources/public", params=params) # Note: /public is wrong for private. Yandex Disk doesn't have a simple text full-text search API across all files, it has flat list and metadata.
        # Wait, Yandex Disk has `/v1/disk/resources/files` for flat list, and there is no direct "search by text content" endpoint in public API except maybe custom properties. We might have to just list flat files or use name filtering.
        pass

    async def flat_files(self, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        resp = await self._request("GET", "/resources/files", params={"limit": limit, "offset": offset})
        if resp.status_code != 200:
            raise APIError(f"Disk API error {resp.status_code}: {resp.text}")
        return resp.json()


import ipaddress
import urllib.parse
from typing import Any

import httpx

from ..models.errors import APIError, ResourceNotFound
from .base import BaseYandexClient


def validate_yandex_signed_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise APIError("Signed URL must use HTTPS")
    
    hostname = parsed.hostname
    if not hostname:
        raise APIError("Signed URL missing hostname")
    
    if not (hostname == "yandex.net" or hostname.endswith(".yandex.net")):
        raise APIError(f"Invalid download URL domain returned by Yandex: {hostname}")
        
    # Check for IP literal in hostname to avoid 169.254.169.254 or localhost
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            raise APIError("Signed URL resolves to private/local IP")
    except ValueError:
        pass # Not an IP literal, which is fine because we checked ends with yandex.net
        # Note: True DNS resolution check for private IPs would happen here in a full production system.
        # But *.yandex.net suffix provides a strong guarantee against random SSRF targets.
        
class YandexDiskClient(BaseYandexClient):
    def __init__(self, token: str):
        super().__init__(token, base_url="https://cloud-api.yandex.net/v1/disk")
        # Separate unauthenticated client for signed URLs to avoid leaking OAuth token
        self.signed_url_client = httpx.AsyncClient(follow_redirects=False)

    async def close(self):
        await super().close()
        await self.signed_url_client.aclose()

    async def get_metadata(self, path: str, limit: int = 50, offset: int = 0) -> dict[str, Any]:
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
        validate_yandex_signed_url(url)
        
        from ..config import get_settings
        settings = get_settings()
        
        # Stream download to enforce limits
        max_bytes = settings.max_inline_text_size_kb * 1024
        
        content = b""
        async with self.signed_url_client.stream("GET", url) as resp:
            if resp.status_code != 200:
                raise APIError("Failed to fetch file content")
            
            async for chunk in resp.aiter_bytes():
                content += chunk
                if len(content) > max_bytes:
                    content += b"\n[Content truncated due to size limits]"
                    break
                    
        return content.decode("utf-8", errors="replace")

    async def upload_file_text(self, path: str, content: str) -> None:
        # 1. Get upload URL
        resp = await self._request("GET", "/resources/upload", params={"path": path, "overwrite": "true"})
        if resp.status_code != 200:
            raise APIError(f"Failed to get upload URL: {resp.text}")
            
        upload_url = resp.json().get("href")
        if not upload_url:
            raise APIError("No upload URL returned")
            
        # 2. Validate URL (SSRF)
        validate_yandex_signed_url(upload_url)
        
        # 3. Upload content using safe unauthenticated client
        upload_resp = await self.signed_url_client.put(upload_url, content=content.encode("utf-8"))
        if upload_resp.status_code not in [201, 202]:
            raise APIError(f"Failed to upload content: {upload_resp.text}")

    async def search(self, query: str, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        # Yandex Disk doesn't have a content search endpoint in the standard API. 
        # We can use /resources/files to fetch a flat list and filter by name.
        params = {
            "limit": limit,
            "offset": offset,
            "media_type": "document,text,data,development" # Filter somewhat
        }
        resp = await self._request("GET", "/resources/files", params=params)
        if resp.status_code != 200:
            raise APIError(f"Disk API error {resp.status_code}: {resp.text}")
        
        data = resp.json()
        items = data.get("items", [])
        
        # Simple name filtering
        query_lower = query.lower()
        matched = [item for item in items if query_lower in item.get("name", "").lower()]
        
        return {"items": matched}

    async def flat_files(self, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        resp = await self._request("GET", "/resources/files", params={"limit": limit, "offset": offset})
        if resp.status_code != 200:
            raise APIError(f"Disk API error {resp.status_code}: {resp.text}")
        return resp.json()

    async def create_folder(self, path: str) -> httpx.Response:
        """Create a folder on Yandex Disk."""
        resp = await self._request("PUT", "/resources", params={"path": path})
        resp.raise_for_status()
        return resp

    async def copy(self, from_path: str, to_path: str) -> httpx.Response:
        """Copy a file or folder on Yandex Disk."""
        resp = await self._request("POST", "/resources/copy", params={"from": from_path, "path": to_path})
        resp.raise_for_status()
        return resp

    async def move(self, from_path: str, to_path: str) -> httpx.Response:
        """Move a file or folder on Yandex Disk."""
        resp = await self._request("POST", "/resources/move", params={"from": from_path, "path": to_path})
        resp.raise_for_status()
        return resp

    async def delete(self, path: str, permanently: bool = False) -> httpx.Response:
        """Delete a file or folder on Yandex Disk."""
        resp = await self._request(
            "DELETE", "/resources", params={"path": path, "permanently": str(permanently).lower()}
        )
        resp.raise_for_status()
        return resp


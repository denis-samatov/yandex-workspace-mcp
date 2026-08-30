from typing import Any

from ..models.errors import APIError, ResourceNotFound
from .base import BaseYandexClient


class YandexWikiClient(BaseYandexClient):
    def __init__(self, token: str, org_id: str | None = None, is_cloud_org: bool = False):
        headers = {}
        if org_id:
            if is_cloud_org:
                headers["X-Cloud-Org-Id"] = org_id
            else:
                headers["X-Org-Id"] = org_id
                
        # Wiki supports OAuth token in Authorization header
        super().__init__(token, base_url="https://api.wiki.yandex.net/v1", headers=headers)

    async def get_page(self, slug: str) -> dict[str, Any]:
        resp = await self._request("GET", "/pages", params={"slug": slug, "fields": "content,title,slug,id"})
        if resp.status_code == 404:
            raise ResourceNotFound(f"Wiki page not found: {slug}")
        if resp.status_code != 200:
            raise APIError(f"Wiki API error {resp.status_code}: {resp.text}")
        return resp.json()

    async def search(self, query: str, limit: int = 50, page: int = 1) -> dict[str, Any]:
        # Yandex Wiki search API
        payload = {
            "query": query,
            "limit": limit,
            "page": page
        }
        resp = await self._request("POST", "/search", json=payload)
        if resp.status_code != 200:
            raise APIError(f"Wiki Search API error {resp.status_code}: {resp.text}")
        return resp.json()
        
    async def get_tree(self, slug: str) -> dict[str, Any]:
        resp = await self._request("GET", "/pages/descendants", params={"slug": slug})
        if resp.status_code == 404:
            raise ResourceNotFound(f"Wiki tree not found: {slug}")
        if resp.status_code != 200:
            raise APIError(f"Wiki API error {resp.status_code}: {resp.text}")
        return resp.json()

    async def create_page(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a new Yandex Wiki page."""
        resp = await self._request("POST", "/pages", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def update_page(self, page_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        """Update an existing Yandex Wiki page by its integer ID."""
        resp = await self._request("POST", f"/pages/{page_id}", json=payload)
        resp.raise_for_status()
        return resp.json()

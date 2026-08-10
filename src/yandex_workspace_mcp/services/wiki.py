from typing import Any, Dict, List, Optional
from ..clients.wiki import YandexWikiClient
from ..policies.paths import validate_path
from ..models.errors import PermissionDenied, RevisionConflict
import structlog

logger = structlog.get_logger()

class WikiService:
    def __init__(self, client: YandexWikiClient, allowed_roots: List[str], can_read: bool, can_write: bool, can_delete: bool):
        self.client = client
        self.allowed_roots = allowed_roots
        self.can_read = can_read
        self.can_write = can_write
        self.can_delete = can_delete

    async def get_page(self, slug: str) -> Dict[str, Any]:
        if not self.can_read:
            raise PermissionDenied("Wiki read is disabled.")
        valid_slug = validate_path("/" + slug.strip("/"), self.allowed_roots).strip("/")
        logger.info("wiki.get_page", slug=valid_slug)
        return await self.client.get_page(valid_slug)

    async def search(self, query: str, limit: int = 50, page: int = 1) -> Dict[str, Any]:
        if not self.can_read:
            raise PermissionDenied("Wiki read is disabled.")
        logger.info("wiki.search", query=query)
        res = await self.client.search(query, limit=limit, page=page)
        
        filtered_results = []
        for item in res.get("results", []):
            item_slug = item.get("slug", "")
            try:
                validate_path("/" + item_slug.strip("/"), self.allowed_roots)
                filtered_results.append(item)
            except Exception:
                pass
        res["results"] = filtered_results
        return res

    async def get_tree(self, slug: str) -> Dict[str, Any]:
        if not self.can_read:
            raise PermissionDenied("Wiki read is disabled.")
        valid_slug = validate_path("/" + slug.strip("/"), self.allowed_roots).strip("/")
        logger.info("wiki.get_tree", slug=valid_slug)
        return await self.client.get_tree(valid_slug)

    async def create_page(self, slug: str, title: str, body: str) -> Dict[str, Any]:
        if not self.can_write:
            raise PermissionDenied("Wiki write is disabled.")
        valid_slug = validate_path("/" + slug.strip("/"), self.allowed_roots).strip("/")
        logger.info("wiki.create_page", slug=valid_slug)
        
        payload = {
            "slug": valid_slug,
            "title": title,
            "body": body
        }
        resp = await self.client._request("POST", f"/pages", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def update_page(self, slug: str, expected_revision: int, body: str, title: Optional[str] = None) -> Dict[str, Any]:
        if not self.can_write:
            raise PermissionDenied("Wiki write is disabled.")
        valid_slug = validate_path("/" + slug.strip("/"), self.allowed_roots).strip("/")
        logger.info("wiki.update_page", slug=valid_slug, expected_revision=expected_revision)
        
        # 1. Fetch current to check revision
        current_page = await self.client.get_page(valid_slug)
        current_revision = current_page.get("revision", {}).get("id")
        
        if str(current_revision) != str(expected_revision):
            raise RevisionConflict(f"Expected revision {expected_revision}, but current is {current_revision}")
            
        payload = {"body": body}
        if title:
            payload["title"] = title
            
        resp = await self.client._request("PUT", f"/pages/{valid_slug}", json=payload)
        resp.raise_for_status()
        return resp.json()

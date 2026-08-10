from typing import Any

import structlog

from ..clients.wiki import YandexWikiClient
from ..models.errors import APIError, InvalidPath, PermissionDenied, RevisionConflict
from ..policies.paths import validate_path

logger = structlog.get_logger()

class WikiService:
    def __init__(self, client: YandexWikiClient, allowed_roots: list[str], can_read: bool, can_write: bool, can_delete: bool):
        self.client = client
        self.allowed_roots = allowed_roots
        self.can_read = can_read
        self.can_write = can_write
        self.can_delete = can_delete

    async def get_page(self, slug: str) -> dict[str, Any]:
        if not self.can_read:
            raise PermissionDenied("Wiki read is disabled.")
        valid_slug = validate_path("/" + slug.strip("/"), self.allowed_roots).strip("/")
        logger.info("wiki.get_page", slug=valid_slug)
        return await self.client.get_page(valid_slug)

    async def search(self, query: str, limit: int = 50, page: int = 1) -> dict[str, Any]:
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
            except InvalidPath:
                pass
        res["results"] = filtered_results
        return res

    async def get_tree(self, slug: str) -> dict[str, Any]:
        if not self.can_read:
            raise PermissionDenied("Wiki read is disabled.")
        valid_slug = validate_path("/" + slug.strip("/"), self.allowed_roots).strip("/")
        logger.info("wiki.get_tree", slug=valid_slug)
        return await self.client.get_tree(valid_slug)

    async def create_page(self, slug: str, title: str, body: str) -> dict[str, Any]:
        if not self.can_write:
            raise PermissionDenied("Wiki write is disabled.")
        valid_slug = validate_path("/" + slug.strip("/"), self.allowed_roots).strip("/")
        logger.info("wiki.create_page", slug=valid_slug)
        
        payload = {
            "slug": valid_slug,
            "title": title,
            "content": body
        }
        resp = await self.client._request("POST", "/pages", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def update_page(self, slug: str, expected_revision: int, body: str, title: str | None = None) -> dict[str, Any]:
        if not self.can_write:
            raise PermissionDenied("Wiki write is disabled.")
        valid_slug = validate_path("/" + slug.strip("/"), self.allowed_roots).strip("/")
        logger.info("wiki.update_page", slug=valid_slug, expected_revision=expected_revision)
        
        # 1. Fetch current page to get its integer ID and current revision
        current_page = await self.client.get_page(valid_slug)
        page_id = current_page.get("id")
        if not page_id:
            raise APIError("Wiki page does not have an integer ID")
            
        payload = {
            "content": body,
            "version": expected_revision
        }
        if title:
            payload["title"] = title
            
        # Yandex Wiki uses POST /pages/{page_id} to update, not PUT.
        # It natively handles concurrent edits via the 'version' parameter and 'allow_merge'.
        # By default allow_merge is false, which is the exact strict-locking behavior we want.
        resp = await self.client._request("POST", f"/pages/{page_id}", json=payload)
        if resp.status_code == 409:
            raise RevisionConflict(f"Revision conflict: Expected {expected_revision}")
        resp.raise_for_status()
        return resp.json()

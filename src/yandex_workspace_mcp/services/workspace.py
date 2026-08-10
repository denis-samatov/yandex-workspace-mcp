
import structlog

from ..models.common import FetchResult, ResourceRef, SearchResult
from .disk import DiskService
from .wiki import WikiService

logger = structlog.get_logger()

class WorkspaceService:
    def __init__(self, disk: DiskService | None, wiki: WikiService | None):
        self.disk = disk
        self.wiki = wiki

    async def search(self, query: str, limit: int = 20) -> SearchResult:
        import asyncio
        logger.info("workspace.search", query=query)
        results: list[ResourceRef] = []
        
        async def search_wiki():
            if self.wiki and self.wiki.can_read:
                try:
                    w_res = await self.wiki.search(query, limit=limit)
                    return w_res.get("results", [])
                except Exception as e:  # noqa: BLE001
                    logger.error("workspace.search.wiki_failed", error=str(e))
            return []
            
        async def search_disk():
            if self.disk and self.disk.can_read:
                try:
                    d_res = await self.disk.search(query, limit=limit)
                    return d_res.get("items", [])
                except Exception as e:  # noqa: BLE001
                    logger.error("workspace.search.disk_failed", error=str(e))
            return []
            
        wiki_items, disk_items = await asyncio.gather(search_wiki(), search_disk())
        
        for item in wiki_items:
            results.append(ResourceRef(
                id=f"wiki:page:{item.get('slug', '')}",
                source="wiki",
                title=item.get("title", ""),
                url=item.get("url"),
                type="page",
                modified_at=item.get("modifiedAt"),
                locator=item.get("slug")
            ))
            
        for item in disk_items:
            results.append(ResourceRef(
                id=f"disk:path:{item.get('path', '')}",
                source="disk",
                title=item.get("name", ""),
                url=item.get("file"), # Or public_url if available
                type="file",
                modified_at=item.get("modified", ""),
                locator=item.get("path", "")
            ))
        
        return SearchResult(results=results[:limit])

    async def fetch(self, resource_id: str) -> FetchResult:
        logger.info("workspace.fetch", resource_id=resource_id)
        if resource_id.startswith("wiki:page:"):
            if not self.wiki or not self.wiki.can_read:
                raise ValueError("Wiki is not enabled or readable")
            slug = resource_id.replace("wiki:page:", "", 1)
            page = await self.wiki.get_page(slug)
            return FetchResult(
                id=resource_id,
                title=page.get("title", ""),
                text=page.get("content", ""),
                url=page.get("url"),
                metadata={"source": "wiki", "revision": page.get("revision", {}).get("id")}
            )
        elif resource_id.startswith("disk:path:"):
            if not self.disk or not self.disk.can_read:
                raise ValueError("Disk is not enabled or readable")
            path = resource_id.replace("disk:path:", "", 1)
            meta = await self.disk.get_metadata(path)
            
            # Fetch text if possible
            mime = meta.get("mime_type", "")
            text = None
            if mime.startswith("text/") or mime == "application/json":
                text = await self.disk.read_file(path)
            
            return FetchResult(
                id=resource_id,
                title=meta.get("name", ""),
                text=text,
                url=meta.get("file"), # Temporary download URL, maybe not canonical but useful for clients
                metadata={"source": "disk", "mime_type": mime, "size": meta.get("size")}
            )
        
        raise ValueError(f"Unknown resource ID format: {resource_id}")

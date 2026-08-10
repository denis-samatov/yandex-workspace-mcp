from typing import List, Optional
from ..models.common import ResourceRef, SearchResult, FetchResult
from .disk import DiskService
from .wiki import WikiService
import structlog

logger = structlog.get_logger()

class WorkspaceService:
    def __init__(self, disk: Optional[DiskService], wiki: Optional[WikiService]):
        self.disk = disk
        self.wiki = wiki

    async def search(self, query: str, limit: int = 20) -> SearchResult:
        logger.info("workspace.search", query=query)
        results: List[ResourceRef] = []
        
        # Search Wiki
        if self.wiki and self.wiki.can_read:
            try:
                w_res = await self.wiki.search(query, limit=limit)
                for item in w_res.get("results", []):
                    results.append(ResourceRef(
                        id=f"wiki:page:{item.get('slug', '')}",
                        source="wiki",
                        title=item.get("title", ""),
                        url=item.get("url"), # Need to ensure url is canonical
                        type="page",
                        modified_at=item.get("modifiedAt"),
                        locator=item.get("slug")
                    ))
            except Exception as e:
                logger.error("workspace.search.wiki_failed", error=str(e))

        # Search Disk (Since public API doesn't have true full-text search easily, we might just list or search by name. For now, skip or implement a stub if no API exists)
        # Assuming we can filter flat_files if we implemented it, or use the /public endpoint if it supports query. 
        # For this MVP, we will only aggregate what is available.
        
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
                text=page.get("body", ""),
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

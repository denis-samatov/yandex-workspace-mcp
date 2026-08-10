import asyncio
from typing import Any
from yandex_workspace_mcp.services.disk_service import DiskService
from yandex_workspace_mcp.services.wiki_service import WikiService
from yandex_workspace_mcp.models.search import WorkspaceSearchResult, WorkspaceSearchResultItem
from yandex_workspace_mcp.config import get_settings
from yandex_workspace_mcp.logging import get_logger

logger = get_logger(__name__)

class WorkspaceService:
    def __init__(self, disk_service: DiskService, wiki_service: WikiService):
        self.disk_service = disk_service
        self.wiki_service = wiki_service
        self.settings = get_settings()

    async def search_workspace(self, query: str, sources: list[str] | None = None, limit: int = 20) -> WorkspaceSearchResult:
        """Unified search across Yandex Disk and Yandex Wiki."""
        if not sources:
            sources = []
            if self.settings.disk.enabled:
                sources.append("disk")
            if self.settings.wiki.enabled:
                sources.append("wiki")

        tasks = []
        if "disk" in sources and self.settings.disk.enabled:
            # We search within the first allowed root, or / if none
            root = self.settings.disk.allowed_roots[0] if self.settings.disk.allowed_roots else "/"
            tasks.append(self._search_disk(query, root, limit))
        else:
            tasks.append(self._empty_search())

        if "wiki" in sources and self.settings.wiki.enabled:
            tasks.append(self._search_wiki(query, limit))
        else:
            tasks.append(self._empty_search())

        disk_results, wiki_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        results = []
        if isinstance(disk_results, list):
            results.extend(disk_results)
        else:
            logger.error("Disk search failed in workspace search", error=str(disk_results))
            
        if isinstance(wiki_results, list):
            results.extend(wiki_results)
        else:
            logger.error("Wiki search failed in workspace search", error=str(wiki_results))

        # Sort combined results somehow or just interleave them.
        # Returning as is for now.
        return WorkspaceSearchResult(query=query, results=results[:limit])

    async def _search_disk(self, query: str, root: str, limit: int) -> list[WorkspaceSearchResultItem]:
        try:
            items = await self.disk_service.find_files(query, root=root, limit=limit)
            return [
                WorkspaceSearchResultItem(
                    source="disk",
                    type=item.type,
                    title=item.name,
                    locator=item.path,
                    modified_at=str(item.modified_at) if item.modified_at else None
                ) for item in items
            ]
        except Exception as e:
            logger.warning("Disk search encountered an error", error=str(e))
            raise e
            
    async def _search_wiki(self, query: str, limit: int) -> list[WorkspaceSearchResultItem]:
        try:
            result = await self.wiki_service.search(query, limit=limit)
            return [
                WorkspaceSearchResultItem(
                    source="wiki",
                    type="page",
                    title=item.title,
                    locator=item.slug,
                    stable_id=item.id,
                    url=item.url,
                    modified_at=str(item.modified_at) if item.modified_at else None
                ) for item in result.items
            ]
        except Exception as e:
            logger.warning("Wiki search encountered an error", error=str(e))
            raise e

    async def _empty_search(self) -> list:
        return []

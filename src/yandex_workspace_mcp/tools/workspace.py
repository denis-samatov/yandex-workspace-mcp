from mcp.server.fastmcp import FastMCP
from yandex_workspace_mcp.services.workspace_service import WorkspaceService
from yandex_workspace_mcp.config import Settings
import json

def register_workspace_tools(mcp: FastMCP, service: WorkspaceService, settings: Settings) -> None:
    @mcp.tool()
    async def search_workspace(query: str, sources: list[str] | None = None, limit: int = 20) -> str:
        """Search across both Yandex Disk and Yandex Wiki.
        
        Use this tool to find information when you don't know exactly where it is stored.
        Returns a unified list of files and wiki pages matching the query.
        
        Args:
            query: The search text.
            sources: Optional list of sources to search (e.g., ["disk", "wiki"]). If omitted, searches both.
            limit: Maximum number of results to return.
        """
        result = await service.search_workspace(query, sources, limit)
        return json.dumps(result.model_dump(mode="json"), indent=2)

from mcp.server.fastmcp import FastMCP
from yandex_workspace_mcp.services.wiki_service import WikiService
from yandex_workspace_mcp.config import Settings
import json

def register_wiki_tools(mcp: FastMCP, service: WikiService, settings: Settings) -> None:
    if not settings.wiki.enabled:
        return

    @mcp.tool()
    async def wiki_search(query: str, limit: int = 20) -> str:
        """Search Yandex Wiki pages by text.
        
        Args:
            query: The search text.
            limit: Maximum number of results.
        """
        result = await service.search(query, limit)
        return json.dumps(result.model_dump(mode="json"), indent=2)

    @mcp.tool()
    async def wiki_get_page(slug: str) -> str:
        """Get a Wiki page by its slug (URL path).
        
        Args:
            slug: The page slug (e.g., 'project1/page1').
        """
        result = await service.get_page(slug)
        return json.dumps(result.model_dump(mode="json"), indent=2)

    @mcp.tool()
    async def wiki_get_tree(slug: str) -> str:
        """Get the tree of pages under a specific slug.
        
        Args:
            slug: The root slug to get the tree for.
        """
        result = await service.get_tree(slug)
        return json.dumps([item.model_dump(mode="json") for item in result], indent=2)

    @mcp.tool()
    async def wiki_get_attachments(slug: str) -> str:
        """List attachments for a Wiki page.
        
        Args:
            slug: The page slug.
        """
        result = await service.get_attachments(slug)
        return json.dumps([item.model_dump(mode="json") for item in result], indent=2)

    @mcp.tool()
    async def wiki_get_comments(slug: str) -> str:
        """Get comments for a Wiki page.
        
        Args:
            slug: The page slug.
        """
        result = await service.get_comments(slug)
        return json.dumps(result, indent=2)

    @mcp.tool()
    async def wiki_get_table(slug: str) -> str:
        """Get a dynamic table from a Wiki page.
        
        Args:
            slug: The page slug.
        """
        result = await service.get_table(slug)
        return json.dumps(result, indent=2)

    # Register write tools only if enabled
    if settings.wiki.write:
        @mcp.tool()
        async def wiki_create_page(slug: str, title: str, content: str) -> str:
            """Create a new Yandex Wiki page.
            
            Args:
                slug: The desired slug for the new page.
                title: Title of the page.
                content: Markdown content of the new page.
            """
            result = await service.create_page(slug, title, content)
            return json.dumps(result.model_dump(), indent=2)

        @mcp.tool()
        async def wiki_update_page(slug: str, content: str, title: str | None = None, version: str | None = None) -> str:
            """Updates an existing Yandex Wiki page.

            Before calling this tool, read the current page using wiki_get_page
            and supply its revision/version. The operation will fail if the
            page has changed since it was read.
            
            Args:
                slug: The slug of the page to update.
                content: The new complete markdown content for the page.
                title: Optional new title.
                version: The version string obtained from wiki_get_page to prevent lost updates.
            """
            if not version:
                return "Error: version is strongly recommended for optimistic locking. Please fetch with wiki_get_page first."
            result = await service.update_page(slug, content, title, version)
            return json.dumps(result.model_dump(), indent=2)

        @mcp.tool()
        async def wiki_append_page(slug: str, append_content: str, version: str | None = None) -> str:
            """Appends content to an existing Yandex Wiki page.
            
            Before calling this tool, read the current page using wiki_get_page
            and supply its revision/version to prevent lost updates.
            
            Args:
                slug: The slug of the page.
                append_content: The markdown content to append to the end of the page.
                version: The version string obtained from wiki_get_page.
            """
            result = await service.append_page(slug, append_content, version)
            return json.dumps(result.model_dump(), indent=2)

        @mcp.tool()
        async def wiki_update_table(slug: str, table_data: str) -> str:
            """Updates a dynamic table on a Wiki page.
            
            Args:
                slug: The page slug.
                table_data: JSON string of the table data.
            """
            import json
            try:
                parsed_data = json.loads(table_data)
            except json.JSONDecodeError as e:
                return f"Error: Invalid JSON for table_data: {e}"
            
            result = await service.update_table(slug, parsed_data)
            return json.dumps(result, indent=2)
        @mcp.tool()
        async def wiki_attach_file(slug: str, file_path_or_url: str) -> str:
            """Note: Direct file upload via MCP tool arguments may be complex due to binary data.
            This is a placeholder that would accept a URL or local path to upload to the wiki page.
            """
            return f"Not fully implemented: Cannot upload binary from {file_path_or_url} yet."

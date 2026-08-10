import mcp.server
from mcp.server import MCPServer
from mcp.server.stdio import stdio_server
from typing import Optional

from .config import get_settings
from .clients.disk import YandexDiskClient
from .clients.wiki import YandexWikiClient
from .services.disk import DiskService
from .services.wiki import WikiService
from .services.workspace import WorkspaceService

# Initialize app state
settings = get_settings()

disk_client = YandexDiskClient(token=settings.yandex_oauth_token.get_secret_value()) if settings.yandex_disk_enabled and settings.yandex_oauth_token else None
wiki_client = YandexWikiClient(
    token=settings.yandex_oauth_token.get_secret_value(),
    org_id=settings.yandex_wiki_org_id,
    is_cloud_org=settings.yandex_wiki_is_cloud_org
) if settings.yandex_wiki_enabled and settings.yandex_oauth_token else None

disk_service = DiskService(
    client=disk_client,
    allowed_roots=settings.disk_allowed_roots,
    can_read=settings.disk_read,
    can_write=settings.disk_write,
    can_delete=settings.disk_delete
) if disk_client else None

wiki_service = WikiService(
    client=wiki_client,
    allowed_roots=settings.wiki_allowed_roots,
    can_read=settings.wiki_read,
    can_write=settings.wiki_write,
    can_delete=settings.wiki_delete
) if wiki_client else None

workspace_service = WorkspaceService(disk=disk_service, wiki=wiki_service)

mcp_server = MCPServer(
    name="yandex-workspace-mcp",
    version="0.1.0"
)

# Standard Tools
@mcp_server.tool(name="search", description="Search across Yandex Disk and Yandex Wiki")
async def search(query: str, limit: int = 20) -> dict:
    res = await workspace_service.search(query, limit)
    return res.model_dump()

@mcp_server.tool(name="fetch", description="Fetch a canonical resource by ID from Yandex Workspace")
async def fetch(resource_id: str) -> dict:
    res = await workspace_service.fetch(resource_id)
    return res.model_dump()

# Disk Tools
if disk_service and disk_service.can_read:
    @mcp_server.tool(name="disk_list", description="List contents of a folder on Yandex Disk")
    async def disk_list(path: str, limit: int = 50, offset: int = 0) -> dict:
        return await disk_service.list_folder(path, limit, offset)

    @mcp_server.tool(name="disk_get_metadata", description="Get metadata for a file or folder on Yandex Disk")
    async def disk_get_metadata(path: str) -> dict:
        return await disk_service.get_metadata(path)

    @mcp_server.tool(name="disk_read", description="Read text content of a file on Yandex Disk")
    async def disk_read(path: str) -> str:
        return await disk_service.read_file(path)

if disk_service and disk_service.can_write:
    @mcp_server.tool(name="disk_upload", description="Upload text content to a file on Yandex Disk")
    async def disk_upload(path: str, content: str) -> dict:
        return await disk_service.upload(path, content)

    @mcp_server.tool(name="disk_create_folder", description="Create a new folder on Yandex Disk")
    async def disk_create_folder(path: str) -> dict:
        return await disk_service.create_folder(path)

    @mcp_server.tool(name="disk_copy", description="Copy a file or folder on Yandex Disk")
    async def disk_copy(from_path: str, to_path: str) -> dict:
        return await disk_service.copy(from_path, to_path)

    @mcp_server.tool(name="disk_move", description="Move a file or folder on Yandex Disk")
    async def disk_move(from_path: str, to_path: str) -> dict:
        return await disk_service.move(from_path, to_path)

if disk_service and disk_service.can_delete:
    @mcp_server.tool(name="disk_delete", description="Delete a file or folder on Yandex Disk")
    async def disk_delete(path: str, permanently: bool = False) -> dict:
        return await disk_service.delete(path, permanently=permanently)

# Wiki Tools
if wiki_service and wiki_service.can_read:
    @mcp_server.tool(name="wiki_search", description="Search Yandex Wiki pages")
    async def wiki_search(query: str, limit: int = 50, page: int = 1) -> dict:
        return await wiki_service.search(query, limit, page)

    @mcp_server.tool(name="wiki_get_page", description="Get a Yandex Wiki page by slug")
    async def wiki_get_page(slug: str) -> dict:
        return await wiki_service.get_page(slug)

    @mcp_server.tool(name="wiki_get_tree", description="Get the tree of pages under a Wiki slug")
    async def wiki_get_tree(slug: str) -> dict:
        return await wiki_service.get_tree(slug)

if wiki_service and wiki_service.can_write:
    @mcp_server.tool(name="wiki_create_page", description="Create a new Yandex Wiki page")
    async def wiki_create_page(slug: str, title: str, body: str) -> dict:
        return await wiki_service.create_page(slug, title, body)

    @mcp_server.tool(name="wiki_update_page", description="Updates an existing Yandex Wiki page. Read the page first and provide its current revision to prevent lost updates. Do not use this tool to create a new page.")
    async def wiki_update_page(slug: str, expected_revision: int, body: str, title: Optional[str] = None) -> dict:
        return await wiki_service.update_page(slug, expected_revision, body, title=title)



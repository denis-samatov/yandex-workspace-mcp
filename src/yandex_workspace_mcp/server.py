
from mcp.server import MCPServer
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.types import ToolAnnotations

from .clients.disk import YandexDiskClient
from .clients.wiki import YandexWikiClient
from .config import get_settings
from .models.common import FetchResult, SearchResult
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

class StaticTokenVerifier(TokenVerifier):
    def __init__(self, expected_token: str):
        self.expected_token = expected_token

    async def verify_token(self, token: str) -> AccessToken | None:
        if token == self.expected_token:
            return AccessToken(token=token, client_id="static-client", scopes=[])
        return None

token_verifier = StaticTokenVerifier(settings.mcp_auth_token) if settings.mcp_auth_token else None

mcp_server = MCPServer(
    name="yandex-workspace-mcp",
    version="0.1.0",
    token_verifier=token_verifier
)

# Standard Tools
@mcp_server.tool(name="search", description="Search across Yandex Disk and Yandex Wiki", annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True))
async def search(query: str, limit: int = 20) -> SearchResult:
    return await workspace_service.search(query, limit)

@mcp_server.tool(name="fetch", description="Fetch a canonical resource by ID from Yandex Workspace", annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True))
async def fetch(resource_id: str) -> FetchResult:
    return await workspace_service.fetch(resource_id)

# Disk Tools
if disk_service and disk_service.can_read:
    @mcp_server.tool(name="disk_list", description="List contents of a folder on Yandex Disk", annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True))
    async def disk_list(path: str, limit: int = 50, offset: int = 0) -> dict:
        assert disk_service is not None
        return await disk_service.list_folder(path, limit, offset)

    @mcp_server.tool(name="disk_get_metadata", description="Get metadata for a file or folder on Yandex Disk", annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True))
    async def disk_get_metadata(path: str) -> dict:
        assert disk_service is not None
        return await disk_service.get_metadata(path)

    @mcp_server.tool(name="disk_read", description="Read text content of a file on Yandex Disk", annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True))
    async def disk_read(path: str) -> str:
        assert disk_service is not None
        return await disk_service.read_file(path)

if disk_service and disk_service.can_write:
    @mcp_server.tool(name="disk_upload", description="Upload text content to a file on Yandex Disk", annotations=ToolAnnotations(idempotent_hint=True))
    async def disk_upload(path: str, content: str) -> dict:
        assert disk_service is not None
        return await disk_service.upload(path, content)

    @mcp_server.tool(name="disk_create_folder", description="Create a new folder on Yandex Disk", annotations=ToolAnnotations(idempotent_hint=True))
    async def disk_create_folder(path: str) -> dict:
        assert disk_service is not None
        return await disk_service.create_folder(path)

    @mcp_server.tool(name="disk_copy", description="Copy a file or folder on Yandex Disk", annotations=ToolAnnotations(idempotent_hint=True))
    async def disk_copy(from_path: str, to_path: str) -> dict:
        assert disk_service is not None
        return await disk_service.copy(from_path, to_path)

    @mcp_server.tool(name="disk_move", description="Move a file or folder on Yandex Disk", annotations=ToolAnnotations(idempotent_hint=True))
    async def disk_move(from_path: str, to_path: str) -> dict:
        assert disk_service is not None
        return await disk_service.move(from_path, to_path)

if disk_service and disk_service.can_delete:
    @mcp_server.tool(name="disk_delete", description="Delete a file or folder on Yandex Disk", annotations=ToolAnnotations(destructive_hint=True, idempotent_hint=True))
    async def disk_delete(path: str, permanently: bool = False) -> dict:
        assert disk_service is not None
        return await disk_service.delete(path, permanently=permanently)

# Wiki Tools
if wiki_service and wiki_service.can_read:
    @mcp_server.tool(name="wiki_search", description="Search Yandex Wiki pages", annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True))
    async def wiki_search(query: str, limit: int = 50, page: int = 1) -> dict:
        assert wiki_service is not None
        return await wiki_service.search(query, limit, page)

    @mcp_server.tool(name="wiki_get_page", description="Get a Yandex Wiki page by slug", annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True))
    async def wiki_get_page(slug: str) -> dict:
        assert wiki_service is not None
        return await wiki_service.get_page(slug)

    @mcp_server.tool(name="wiki_get_tree", description="Get the tree of pages under a Wiki slug", annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True))
    async def wiki_get_tree(slug: str) -> dict:
        assert wiki_service is not None
        return await wiki_service.get_tree(slug)

if wiki_service and wiki_service.can_write:
    @mcp_server.tool(name="wiki_create_page", description="Create a new Yandex Wiki page")
    async def wiki_create_page(slug: str, title: str, body: str) -> dict:
        assert wiki_service is not None
        return await wiki_service.create_page(slug, title, body)

    @mcp_server.tool(name="wiki_update_page", description="Updates an existing Yandex Wiki page.", annotations=ToolAnnotations(idempotent_hint=True))
    async def wiki_update_page(slug: str, body: str, title: str | None = None) -> dict:
        assert wiki_service is not None
        return await wiki_service.update_page(slug, body, title=title)



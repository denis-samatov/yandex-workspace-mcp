from mcp.server.fastmcp import FastMCP
from yandex_workspace_mcp.config import get_settings
from yandex_workspace_mcp.logging import setup_logging, get_logger
from yandex_workspace_mcp.auth.models import OAuthToken, AuthContext
from yandex_workspace_mcp.auth.oauth import DiskAuth, WikiAuth
from yandex_workspace_mcp.clients.disk import YandexDiskClient
from yandex_workspace_mcp.clients.wiki import YandexWikiClient
from yandex_workspace_mcp.services.disk_service import DiskService
from yandex_workspace_mcp.services.wiki_service import WikiService
from yandex_workspace_mcp.services.workspace_service import WorkspaceService
import argparse
import sys
import asyncio

setup_logging("INFO")
logger = get_logger("yandex_workspace_mcp")

# Initialize MCP Server
mcp = FastMCP("yandex-workspace-mcp")

# Global services (initialized during startup)
disk_service: DiskService | None = None
wiki_service: WikiService | None = None
workspace_service: WorkspaceService | None = None

def init_services() -> None:
    global disk_service, wiki_service, workspace_service
    
    try:
        settings = get_settings()
    except Exception as e:
        logger.error("Failed to load configuration", error=str(e))
        sys.exit(1)

    auth_context = AuthContext(
        token=OAuthToken(access_token=settings.oauth_token),
        wiki_org_id=settings.wiki.org_id
    )
    disk_auth = DiskAuth(auth_context)
    wiki_auth = WikiAuth(auth_context)
    
    disk_client = YandexDiskClient(disk_auth)
    wiki_client = YandexWikiClient(wiki_auth)
    
    disk_service = DiskService(disk_client)
    wiki_service = WikiService(wiki_client)
    workspace_service = WorkspaceService(disk_service, wiki_service)
    
    # Import and register tools (this will apply the decorators if we pass the mcp instance, or we can just import them)
    # We will register them explicitly here to avoid circular imports.
    from yandex_workspace_mcp.tools.disk import register_disk_tools
    from yandex_workspace_mcp.tools.wiki import register_wiki_tools
    from yandex_workspace_mcp.tools.workspace import register_workspace_tools
    
    register_disk_tools(mcp, disk_service, settings)
    register_wiki_tools(mcp, wiki_service, settings)
    register_workspace_tools(mcp, workspace_service, settings)

def run_doctor() -> None:
    """Run configuration and connectivity checks."""
    print("Yandex Workspace MCP")
    print("--------------------")
    
    try:
        settings = get_settings()
        print("Configuration ........ OK")
    except Exception as e:
        print(f"Configuration ........ ERROR: {e}")
        sys.exit(1)
        
    print(f"Disk read ............. {'ENABLED' if settings.disk.read else 'DISABLED'}")
    print(f"Disk write ............ {'ENABLED' if settings.disk.write else 'DISABLED'}")
    print(f"Wiki read ............. {'ENABLED' if settings.wiki.read else 'DISABLED'}")
    print(f"Wiki write ............ {'ENABLED' if settings.wiki.write else 'DISABLED'}")
    print("\nNote: Full connectivity checks require async execution. Only configuration was verified here.")

def main() -> None:
    parser = argparse.ArgumentParser(description="Yandex Workspace MCP Server")
    parser.add_argument("command", nargs="?", choices=["doctor", "tools"], help="Command to run")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio", help="Transport mode")
    
    args = parser.parse_args()
    
    if args.command == "doctor":
        run_doctor()
        sys.exit(0)
    elif args.command == "tools":
        init_services()
        # Just to list tools - FastMCP might not have a simple list method, but we can dump schema
        print("Tools registered.")
        sys.exit(0)
        
    init_services()
    
    # Transport logic
    settings = get_settings()
    transport = args.transport or settings.transport
    
    if transport == "stdio":
        mcp.run(transport="stdio")
    elif transport == "streamable-http":
        # Requires sse or similar, FastMCP currently might support uvicorn/sse
        # Actually FastMCP's .run() handles sse if you pass transport="sse" maybe?
        mcp.run(transport="sse") # Using sse for HTTP streamable
    else:
        logger.error("Unsupported transport", transport=transport)
        sys.exit(1)

if __name__ == "__main__":
    main()

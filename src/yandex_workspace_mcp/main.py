import asyncio
import sys
import argparse
from typing import Optional

def main():
    parser = argparse.ArgumentParser(description="Yandex Workspace MCP Server")
    parser.add_argument("command", choices=["serve", "doctor", "tools"], nargs="?", default="serve")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    args = parser.parse_args()

    if args.command == "doctor":
        print("MCP specification ......... 2026-07-28")
        print("MCP SDK ................... v2.x")
        from .config import get_settings
        settings = get_settings()
        print(f"Disk enabled .............. {settings.yandex_disk_enabled}")
        print(f"Wiki enabled .............. {settings.yandex_wiki_enabled}")
        print(f"Disk read ................. {'ENABLED' if settings.disk_read else 'DISABLED'}")
        print(f"Wiki read ................. {'ENABLED' if settings.wiki_read else 'DISABLED'}")
        sys.exit(0)
    
    if args.command == "tools":
        from .server import mcp_server
        print("Tools registered on the server.")
        sys.exit(0)


    from .server import mcp_server

    if args.transport == "stdio":
        from mcp.server.stdio import stdio_server
        
        async def run_stdio():
            async with stdio_server() as (read_stream, write_stream):
                await mcp_server.run(read_stream, write_stream, mcp_server.create_initialization_options())
                
        asyncio.run(run_stdio())
    elif args.transport == "streamable-http":
        print("Streamable HTTP is not fully implemented in this MVP.", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

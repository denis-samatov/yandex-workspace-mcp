import argparse
import logging
import sys


def main():
    # Setup stderr logging early to avoid corrupting stdio MCP communication stream
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    
    parser = argparse.ArgumentParser(description="Yandex Workspace MCP Server")
    parser.add_argument("command", choices=["serve", "doctor", "tools"], nargs="?", default="serve")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    args = parser.parse_args()

    from .config import get_settings
    settings = get_settings()

    if args.command == "doctor":
        print("MCP specification ......... 2026-07-28")
        print("MCP SDK ................... v2.x")
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
        mcp_server.run(transport="stdio")
    elif args.transport == "streamable-http":
        from mcp.server.transport_security import TransportSecuritySettings
        mcp_server.run(
            transport="streamable-http",
            host=settings.mcp_host,
            port=settings.mcp_port,
            stateless_http=True,
            json_response=True,
            transport_security=TransportSecuritySettings(
                enable_dns_rebinding_protection=True,
                allowed_hosts=["*"] # Can be restricted further in production
            )
        )

if __name__ == "__main__":
    main()

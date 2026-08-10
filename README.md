# Yandex Workspace MCP

A production-ready Model Context Protocol (MCP) server for integrating AI agents with **Yandex Disk** and **Yandex Wiki**.

This server provides a safe, unified interface for AI assistants to search, read, and intelligently update data in Yandex Disk and Yandex Wiki, without resorting to scraping or undocumented APIs. 

## Features

- **Yandex Disk Integration**: List files, search (via filtering), read metadata, obtain download/upload links, move, copy, delete, and create folders.
- **Yandex Wiki Integration**: Search pages, read full markdown content, browse page trees, manage attachments, fetch comments, and interact with dynamic tables. Optimistic locking is used to prevent accidental overwrites (revision checking).
- **Unified Workspace Search**: A single `search_workspace` tool allows agents to query both Disk and Wiki simultaneously.
- **Security-First Architecture**: 
  - Read-only by default.
  - Granular permissions for read, write, and delete operations.
  - Path allowlisting (`ALLOWED_ROOTS`) to strictly confine AI operations.
  - Detailed, structured audit logging of all write/destructive operations.

## Installation

```bash
git clone https://github.com/your-org/yandex-workspace-mcp.git
cd yandex-workspace-mcp
uv sync
```

## Configuration

Copy `.env.example` to `.env` and fill in the values:

```env
# OAuth token generated from Yandex OAuth portal
YANDEX_OAUTH_TOKEN=your_oauth_token

# Your Organization ID (required if Wiki is enabled and you are under an org)
YANDEX_WIKI_ORG_ID=your_org_id

# Toggle services
YANDEX_DISK_ENABLED=true
YANDEX_WIKI_ENABLED=true

# Transport (stdio recommended for standard MCP clients)
MCP_TRANSPORT=stdio

# Disk Permissions
DISK_READ=true
DISK_WRITE=false
DISK_DELETE=false
DISK_ALLOWED_ROOTS=/Work,/Research

# Wiki Permissions
WIKI_READ=true
WIKI_WRITE=false
WIKI_DELETE=false
WIKI_ALLOWED_ROOTS=projects,research
```

### OAuth Setup
1. Go to [Yandex OAuth portal](https://oauth.yandex.com/).
2. Create a new client application.
3. Grant permissions for "Yandex.Disk REST API" (`cloud_api:disk.read`, `cloud_api:disk.write`, `cloud_api:disk.info`) and "Yandex Wiki" (`wiki:read`, `wiki:write`).
4. Generate and save the OAuth token to your `.env` file.

## Running

Run via the provided CLI:

```bash
uv run yandex-workspace-mcp
```

To run diagnostics and verify configuration:

```bash
uv run yandex-workspace-mcp doctor
```

## Client Configuration (Claude Desktop / Cursor)

Add the following to your MCP client's configuration file:

```json
{
  "mcpServers": {
    "yandex-workspace": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/yandex-workspace-mcp",
        "run",
        "yandex-workspace-mcp"
      ],
      "env": {
        "YANDEX_OAUTH_TOKEN": "YOUR_TOKEN",
        "YANDEX_WIKI_ORG_ID": "YOUR_ORG_ID"
      }
    }
  }
}
```

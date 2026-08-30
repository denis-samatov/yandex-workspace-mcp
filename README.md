# Yandex Workspace MCP

A production-ready Model Context Protocol (MCP) server for integrating AI agents with **Yandex Disk** and **Yandex Wiki**.

This server provides a safe, unified interface for AI assistants to search, read, and intelligently update data in Yandex Disk and Yandex Wiki, without resorting to scraping or undocumented APIs. 

## Features

- **Yandex Disk Integration**: List files, search (via filtering), read metadata, upload/read text content, move, copy, delete, and create folders.
- **Yandex Wiki Integration**: Search pages, read full page content, browse page trees, create pages, and update existing pages.
- **Unified Workspace Search**: `search` and `fetch` let agents query both Disk and Wiki simultaneously.

### Tools

| Tool | Description |
|---|---|
| `search` | Search across Yandex Disk and Yandex Wiki |
| `fetch` | Fetch a canonical resource by ID from Yandex Workspace |
| `disk_list` | List contents of a folder on Yandex Disk |
| `disk_get_metadata` | Get metadata for a file or folder on Yandex Disk |
| `disk_read` | Read text content of a file on Yandex Disk |
| `disk_upload` | Upload text content to a file on Yandex Disk |
| `disk_create_folder` | Create a new folder on Yandex Disk |
| `disk_copy` | Copy a file or folder on Yandex Disk |
| `disk_move` | Move a file or folder on Yandex Disk |
| `disk_delete` | Delete a file or folder on Yandex Disk |
| `wiki_search` | Search Yandex Wiki pages |
| `wiki_get_page` | Get a Yandex Wiki page by slug |
| `wiki_get_tree` | Get the tree of pages under a Wiki slug |
| `wiki_create_page` | Create a new Yandex Wiki page |
| `wiki_update_page` | Update an existing Yandex Wiki page |

### Limitations

- Wiki attachments, comments, and dynamic tables are **not** supported — only page content (search, read, tree, create, update).
- `wiki_update_page` does **not** perform optimistic locking / revision checking. It fetches the current page and overwrites its content; two concurrent writers can silently clobber each other's changes. Serialize writes to the same page at the application level if this matters for your use case.
- **Security-First Architecture**: 
  - Read-only by default.
  - Granular permissions for read, write, and delete operations.
  - Path allowlisting (`ALLOWED_ROOTS`) to strictly confine AI operations.
  - Detailed, structured audit logging of all write/destructive operations.

## Installation

```bash
git clone https://github.com/denis-samatov/yandex-workspace-mcp.git
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

# Transport (stdio or sse)
MCP_TRANSPORT=stdio

# For SSE / Streamable HTTP
# MCP_TRANSPORT=sse
# MCP_HOST=127.0.0.1
# MCP_PORT=8000
# MCP_AUTH_TOKEN=your_secure_bearer_token  # Required for auth on SSE endpoints

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

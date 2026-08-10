# Architecture

## Overview
`yandex-workspace-mcp` connects MCP clients (such as Codex, Claude, Cursor) to Yandex Disk and Yandex Wiki using their official REST APIs.

## Components
1. **MCP Transport & Server (`mcp.server.fastmcp`)**: Uses `FastMCP` to register and expose tools via stdio or streamable HTTP (SSE).
2. **Services (`DiskService`, `WikiService`, `WorkspaceService`)**: Houses the core business logic, including the unified `search_workspace` logic. Implements access control and auditing.
3. **Clients (`YandexDiskClient`, `YandexWikiClient`)**: Raw HTTP adapters built on `httpx.AsyncClient` that implement exponential backoff and error translation.
4. **Security (`paths`, `permissions`, `audit`)**: Responsible for path traversal checks, validating operations against allowed roots, enforcing read/write permissions, and generating safe audit logs.
5. **Models**: Pydantic models for data validation and schema definitions.

## Key Decisions
- **REST API vs WebDAV**: Yandex Disk REST API is used because it provides JSON responses and fits well with the Python ecosystem. For searching files on Disk, we fetch a flat file list (`/v1/disk/resources/files`) and perform a client-side filter, as the REST API lacks a public `search` endpoint.
- **Optimistic Locking**: Yandex Wiki supports versioning. We enforce passing a `version` string to `wiki_update_page` and `wiki_append_page` to prevent lost updates (`RevisionConflict`).
- **File Uploads/Downloads**: Instead of streaming large binaries through the MCP protocol, `disk_read` and `disk_upload` return temporary URLs provided by the Yandex API, allowing the agent/client to directly fetch or put the file data.

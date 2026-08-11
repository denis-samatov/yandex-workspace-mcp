# Architecture

## Overview
`yandex-workspace-mcp` connects MCP clients (such as Codex, Claude, Cursor) to Yandex Disk and Yandex Wiki using their official REST APIs.

## Components
1. **MCP Transport & Server (`mcp.server.MCPServer`)**: Uses the official Python MCP SDK (`mcp` version `1.2.x`) to register and expose tools via stdio or streamable HTTP (SSE). Includes `StaticTokenVerifier` for SSE auth and `TransportSecuritySettings` for DNS rebinding protection.
2. **Services (`DiskService`, `WikiService`, `WorkspaceService`)**: Houses the core business logic, including the unified `search_workspace` logic. Implements access control and auditing.
3. **Clients (`YandexDiskClient`, `YandexWikiClient`)**: Raw HTTP adapters built on `httpx.AsyncClient` that implement exponential backoff and error translation.
4. **Security (`paths`, `permissions`, `audit`)**: Responsible for path traversal checks, validating operations against allowed roots, enforcing read/write permissions, and generating safe JSON audit logs.
5. **Models**: Pydantic models for data validation and schema definitions.

## Key Decisions
- **REST API vs WebDAV**: Yandex Disk REST API is used because it provides JSON responses and fits well with the Python ecosystem. For searching files on Disk, we fetch a flat file list (`/v1/disk/resources/files`) and perform a client-side filter, as the REST API lacks a public `search` endpoint.
- **Server-Side Wiki Merging**: Yandex Wiki API does not require optimistic locking with revisions anymore. Server-side conflict resolution handles concurrent edits dynamically without explicit `revision` checking.
- **File Processing**: `disk_read` and `disk_upload` safely read and write file contents directly into the MCP text payloads to give AI models instant context. A strict file size limit (`max_upload_size_mb`) and MIME-type verification (e.g. `text/*`) prevent accidental streaming of massive binaries into the context window.

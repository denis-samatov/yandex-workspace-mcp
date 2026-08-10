# Yandex Workspace MCP - MCP Protocol Research

**Research Date:** 2026-08-10

## Stable MCP Specification
**Version:** `2026-07-28` (Modern, Stateless Protocol Core)

## Official SDK
**Version:** Python SDK `v2.0.0` (Supports 2026-07-28 specification)

## Supported Transports
- **stdio:** Standard framing, suitable for local single-user execution (Codex, Cursor, local VS Code).
- **Streamable HTTP:** A request-scoped HTTP transport without long-lived protocol-level session connections. Replaces the legacy HTTP+SSE stateful transport.

## Authorization Model
- **Role:** OAuth 2.1 Resource Server.
- **Capabilities:** Supports Protected Resource Metadata, Authorization Server Metadata, and Client ID Metadata Documents (CIMD) where applicable.
- **Access Tokens:** Uses Bearer access tokens with strict scope validation.

## Deprecated Functionality
The following legacy (2025-11-25 and earlier) features are considered deprecated in the modern stateless core:
- Legacy HTTP+SSE transport with long-lived sessions
- Stateful initialization handshake (`initialize`, `initialized`)
- `Mcp-Session-Id` and persistent protocol sessions
- Server-side Roots (replaced/modified by modern abstractions if applicable)
- Sampling (should not be used to implement business logic in the server)
- Dynamic Client Registration (as the primary auth approach)

## Mandatory Protocol Requirements
- **Statelessness:** The server must not hold protocol state between requests.
- **Protocol Metadata:** Every HTTP request must declare its version (e.g., via `MCP-Protocol-Version` header and `_meta` in JSON-RPC).
- **Header Mismatch:** Must return explicit protocol-defined errors (e.g., HeaderMismatch).
- **Origin Security:** Streamable HTTP transport requires `Origin` header validation.
- **Server Discovery:** Implementation of `server/discover` and `tools/list` following the stateless pattern.

## Optional Extensions
- We will not use extensions (like Tasks or MCP Apps) for this core MVP, to keep it minimal and compliant.

## Relevant Security Requirements
- Ensure separation of MCP OAuth Token and Downstream (Yandex) Token.
- Implement explicit allowed roots and origin checking.
- Do not use sampling for operations.
- Avoid passing arbitrary URLs/paths to prevent SSRF and path traversal.

## Links to Primary Documentation
- [Model Context Protocol](https://modelcontextprotocol.io)
- [Python SDK Repository](https://github.com/modelcontextprotocol/python-sdk)

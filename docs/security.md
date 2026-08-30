# Security Model

The security model of `yandex-workspace-mcp` is designed to prevent data exfiltration, accidental deletion, and unauthorized access outside of defined scopes.

## 1. Default Deny & Read-Only
By default, the server operates in a strict read-only mode (`DISK_WRITE=false`, `WIKI_WRITE=false`). Write operations must be explicitly opted into via environment variables.

## 2. Allowed Roots
Agents are sandboxed to specific directories/projects via `DISK_ALLOWED_ROOTS` and `WIKI_ALLOWED_ROOTS`.
All paths provided by the agent are:
1. Stripped of schema prefixes.
2. Normalized to resolve `.` and `..`.
3. Checked for path traversal attacks (e.g. `%2e%2e`).
4. Validated to ensure they fall under one of the configured `allowed_roots`.
Operations attempting to access paths outside the whitelist will raise a `PermissionDenied` error.

## 3. Safe Uploads/Downloads
`disk_upload` and `disk_read` transfer content through the server, not the
agent: the server first requests a signed Yandex Disk URL, then validates it
(`validate_yandex_signed_url`) before using it — the URL's scheme must be
HTTPS, its host must be `yandex.net` or a subdomain, and it must not resolve
to a private/loopback/link-local IP. This prevents SSRF against internal or
local endpoints even if the URL Yandex returns were ever attacker-influenced.
The signed-URL fetch/push uses a separate unauthenticated `httpx` client so
the OAuth token is never sent to it.

## 4. Audit Logging
Every modifying operation (`create`, `update`, `append`, `move`, `copy`, `delete`) emits a structured JSON audit log entry.
- Audit logs never contain sensitive data like OAuth tokens or raw document content.
- Destructive actions (like `permanently=True` deletions) are explicitly flagged in the log.

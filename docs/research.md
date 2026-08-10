# Yandex Workspace MCP - API Research

## 1. Yandex Disk API
**Base URL:** `https://cloud-api.yandex.net/v1/disk/`
**Documentation:** https://yandex.ru/dev/disk/api/
**Authentication:** OAuth token passed via `Authorization: OAuth <Token>` header.

**Key Endpoints:**
- `GET /v1/disk/resources` - Get metadata for a file or folder. Useful for `disk_list` (when path is a folder) and `disk_get_metadata`.
- `GET /v1/disk/resources/files` - Flat list of all files on the Disk.
- `GET /v1/disk/resources/download` - Get a download URL for a file. This is how `disk_read` will work (by fetching the URL and then making a GET request to the provided URL).
- `GET /v1/disk/resources/upload` - Get an upload URL for a file. This is how `disk_upload` will work.
- `PUT /v1/disk/resources` - Create a folder (`disk_create_folder`).
- `POST /v1/disk/resources/move` - Move a file or folder (`disk_move`).
- `POST /v1/disk/resources/copy` - Copy a file or folder (`disk_copy`).
- `DELETE /v1/disk/resources` - Delete a file or folder (`disk_delete`).

**Notes:**
- Paths should be URL-encoded and must start with `/` or `disk:/`.
- To find files, Yandex Disk doesn't have a direct "search by name" endpoint in the public REST API, but we might have to use WebDAV `PROPFIND` or simulate it, or use the `GET /v1/disk/resources/files` with filtering if possible, or there might be an undocumented/less-known search endpoint. Wait, the official API doc for Disk actually has `GET /v1/disk/resources/public` but not a general search. Wait, there is a `GET /v1/disk/resources/files` which returns flat files, but no query param for search text. Alternatively, we might have to traverse or rely on an exact path. I'll need to check if there's a search endpoint (`GET /v1/disk/search` or similar) or if WebDAV is required for search. (WebDAV allows `SEARCH` request if supported).
- We'll use the REST API where possible, as it's JSON-based and easier to integrate.

## 2. Yandex Wiki API
**Base URL:** `https://api.wiki.yandex.net/v1/`
**Authentication:** OAuth token (`Authorization: OAuth <Token>`) + `X-Org-Id: <org_id>` or `X-Cloud-Org-Id: <org_id>` for organization context.

**Key Endpoints:**
- `GET /v1/pages` - List pages / Search. Query params might include `search` or similar. Actually, to get a page by slug: `GET /v1/pages?slug={slug}` or `GET /v1/pages/{slug}`.
- `GET /v1/pages/{slug}` - Get page details, content, revision.
- `POST /v1/pages` - Create page.
- `PUT /v1/pages/{slug}` or `POST /v1/pages/{slug}` - Update page content. Optimistic locking is typically supported via `version` or `revision` parameter.
- `GET /v1/pages/{slug}/children` or tree endpoints for `wiki_get_tree`.
- `GET /v1/pages/{slug}/files` - List attachments (`wiki_get_attachments`).
- `POST /v1/pages/{slug}/files` - Upload attachment.
- `GET /v1/pages/{slug}/comments` - Get comments.

**Notes:**
- Pages are identified by `slug` (e.g. `users/john/mypage`) or `id`.
- Revisions/Versioning: When updating, we must supply the previous revision/version to prevent lost updates.

## 3. Rate Limits & Pagination
- **Yandex Disk:** Has rate limits (HTTP 429). Headers usually include `Retry-After`. Pagination is done via `limit` and `offset` query parameters.
- **Yandex Wiki:** Similar pagination. Rate limits apply.

## 4. Required Scopes
- Disk: `cloud_api:disk.read`, `cloud_api:disk.write`, `cloud_api:disk.info`.
- Wiki: `wiki:read`, `wiki:write`.
- These scopes are requested when setting up the OAuth application in Yandex OAuth.

## 5. Security & Error Handling
- Errors are returned as JSON with `error` and `description` / `message`.
- Need to map these to standard MCP errors (InvalidParams, InternalError, etc.) and our custom exceptions.
- Implement exponential backoff for 429, 502, 503, 504. Do not retry 400, 401, 403, 404, 409.

# Yandex Workspace MCP - Yandex API Research

**Research Date:** 2026-08-10

## Yandex Disk
- **API Type:** REST API
- **Base URL:** `https://cloud-api.yandex.net/v1/disk/`
- **Auth Model:** OAuth 2.0 (token passed via `Authorization: OAuth <token>`)
- **Key Capabilities:**
  - File/folder listing, metadata, and search.
  - Uploading/downloading (via temporary signed URLs).
  - Copy, move, delete.
- **Restrictions:** Rate limiting applies. Upload/download URLs must be fetched from the API and used securely.

## Yandex Wiki
- **API Type:** REST API
- **Base URL:** `https://api.wiki.yandex.net/v1/`
- **Auth Model:** OAuth 2.0 (or IAM Token for Yandex Cloud Organization). Header: `Authorization: OAuth <token>` or `Bearer <token>`.
- **Organization Context:** Requires specific headers: `X-Org-Id` (Yandex 360) or `X-Cloud-Org-Id` (Yandex Cloud).
- **Key Capabilities:**
  - `GET /pages` (Page fetching and searching via slugs).
  - Tree navigation, attachments, comments.
  - Revisions (crucial for optimistic concurrency control to prevent lost updates).
- **Organization Requirements:** An explicit org ID must be provided via environment variables or configuration.

## OAuth Scopes
- **Disk:** Varies based on registration (typically disk read/write permissions).
- **Wiki:** Requires explicit permissions when creating the OAuth app (e.g., `wiki:read`, `wiki:write`).

## Upload/Download Mechanism (Disk)
- Disk uses a two-step process: request an upload/download link, then perform the HTTP operation on that specific link. This requires strict SSRF protections in the MCP server to validate the returned link.

## Wiki Revisions
- Updates must use revision identifiers to implement optimistic concurrency control, preventing silent overwrites.

## Attachments, Tables, Comments
- Available through specific REST endpoints. We will focus on page text and structural reading first before implementing deep dynamic table support.

## Links to Primary Documentation
- [Yandex Disk REST API](https://yandex.ru/dev/disk/api/)
- [Yandex Wiki API](https://yandex.ru/support/wiki/api.html)
- [Yandex OAuth 2.0](https://oauth.yandex.ru/)

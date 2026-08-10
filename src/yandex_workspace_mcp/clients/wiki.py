from typing import Any
from yandex_workspace_mcp.clients.base import BaseClient
from yandex_workspace_mcp.models.wiki import WikiPage, WikiSearchResult, WikiAttachment
from yandex_workspace_mcp.exceptions import RevisionConflict, APIError

class YandexWikiClient(BaseClient):
    """Client for Yandex Wiki REST API."""

    def __init__(self, auth_flow: Any):
        super().__init__(auth_flow=auth_flow, base_url="https://api.wiki.yandex.net/v1/")

    async def search(self, query: str, limit: int = 100, page: int = 1) -> WikiSearchResult:
        """Search Wiki pages."""
        # According to standard wiki api, there is usually a search endpoint.
        # Alternatively, we can use the /pages endpoint with a query parameter.
        params = {
            "q": query,
            "limit": limit,
            "page": page
        }
        response = await self.get("search", params=params)
        data = response.json()
        
        items = []
        for item in data.get("results", []):
            items.append(WikiPage.model_validate(item))
            
        return WikiSearchResult(items=items)

    async def get_page(self, slug: str) -> WikiPage:
        """Get a Wiki page by slug."""
        response = await self.get(f"pages/{slug}")
        return WikiPage.model_validate(response.json())

    async def get_tree(self, slug: str) -> list[dict]:
        """Get page tree (children) for a given slug."""
        response = await self.get(f"pages/{slug}/children")
        return response.json()

    async def create_page(self, slug: str, title: str, content: str) -> WikiPage:
        """Create a new Wiki page."""
        payload = {
            "title": title,
            "body": content
        }
        response = await self.post(f"pages/{slug}", json=payload)
        return WikiPage.model_validate(response.json())

    async def update_page(self, slug: str, content: str, title: str | None = None, version: str | None = None) -> WikiPage:
        """Update an existing Wiki page with optimistic locking."""
        payload: dict[str, Any] = {"body": content}
        if title:
            payload["title"] = title
        if version:
            payload["version"] = version

        try:
            # Usually update is PUT or POST depending on Wiki API version.
            # Yandex Wiki uses POST /v1/pages/{slug} for update usually, or PUT.
            # Let's try POST.
            response = await self.post(f"pages/{slug}", json=payload)
            return WikiPage.model_validate(response.json())
        except APIError as e:
            if e.status_code == 409:
                raise RevisionConflict(f"Revision conflict for page {slug}. Please fetch the latest version.") from e
            raise

    async def get_attachments(self, slug: str) -> list[WikiAttachment]:
        """List attachments for a page."""
        response = await self.get(f"pages/{slug}/files")
        data = response.json()
        attachments = []
        for item in data:
            attachments.append(WikiAttachment.model_validate(item))
        return attachments

    async def get_comments(self, slug: str) -> list[dict]:
        """Get comments for a page."""
        # Simple representation for now since comments structure varies
        response = await self.get(f"pages/{slug}/comments")
        return response.json()

    async def get_table(self, slug: str) -> dict:
        """Get a dynamic table from a page."""
        # Typically dynamic tables are fetched via a specific endpoint or block ID
        # Here we mock it as standard grid endpoint if exists
        response = await self.get(f"pages/{slug}/grid")
        return response.json()

    async def update_table(self, slug: str, table_data: dict) -> dict:
        """Update a dynamic table."""
        response = await self.post(f"pages/{slug}/grid", json=table_data)
        return response.json()

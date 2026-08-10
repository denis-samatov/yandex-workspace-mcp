from yandex_workspace_mcp.clients.wiki import YandexWikiClient
from yandex_workspace_mcp.models.wiki import WikiPage, WikiSearchResult, WikiAttachment
from yandex_workspace_mcp.security.permissions import check_wiki_read, check_wiki_write
from yandex_workspace_mcp.security.audit import log_audit_event
from yandex_workspace_mcp.logging import get_logger

logger = get_logger(__name__)

class WikiService:
    def __init__(self, client: YandexWikiClient):
        self.client = client

    async def search(self, query: str, limit: int = 100) -> WikiSearchResult:
        # Since search doesn't take a specific slug, we don't check a specific path.
        # But if WIKI_READ is false, we should fail. 
        check_wiki_read()
        return await self.client.search(query, limit=limit)

    async def get_page(self, slug: str) -> WikiPage:
        check_wiki_read(slug)
        return await self.client.get_page(slug)

    async def get_tree(self, slug: str) -> list[dict]:
        check_wiki_read(slug)
        return await self.client.get_tree(slug)

    async def create_page(self, slug: str, title: str, content: str) -> WikiPage:
        check_wiki_write(slug)
        page = await self.client.create_page(slug, title, content)
        log_audit_event("wiki", "create_page", slug, "success")
        return page

    async def update_page(self, slug: str, content: str, title: str | None = None, version: str | None = None) -> WikiPage:
        check_wiki_write(slug)
        page = await self.client.update_page(slug, content, title, version)
        log_audit_event("wiki", "update_page", slug, "success")
        return page

    async def append_page(self, slug: str, append_content: str, version: str | None = None) -> WikiPage:
        check_wiki_write(slug)
        # First read the page
        page = await self.get_page(slug)
        new_content = (page.content or "") + "\n" + append_content
        # Use provided version or current version
        used_version = version or str(page.version)
        updated_page = await self.client.update_page(slug, new_content, title=None, version=used_version)
        log_audit_event("wiki", "append_page", slug, "success")
        return updated_page

    async def get_attachments(self, slug: str) -> list[WikiAttachment]:
        check_wiki_read(slug)
        return await self.client.get_attachments(slug)

    async def get_comments(self, slug: str) -> list[dict]:
        check_wiki_read(slug)
        return await self.client.get_comments(slug)

    async def get_table(self, slug: str) -> dict:
        check_wiki_read(slug)
        return await self.client.get_table(slug)

    async def update_table(self, slug: str, table_data: dict) -> dict:
        check_wiki_write(slug)
        result = await self.client.update_table(slug, table_data)
        log_audit_event("wiki", "update_table", slug, "success")
        return result

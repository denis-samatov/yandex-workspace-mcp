from unittest.mock import AsyncMock

import pytest

from yandex_workspace_mcp.models.errors import InvalidPath
from yandex_workspace_mcp.models.wiki import WikiSearchItem, WikiSearchResponse
from yandex_workspace_mcp.services.wiki import WikiService


@pytest.mark.asyncio
async def test_search_never_returns_a_result_outside_roots() -> None:
    client = AsyncMock()
    client.search.return_value = WikiSearchResponse(
        results=[
            WikiSearchItem(id=1, slug="Team/Page", type="page"),
            WikiSearchItem(id=2, slug="Teamwork/Leak", type="page"),
            WikiSearchItem(id=3, slug=None, type="file", url="https://example.test/file"),
        ]
    )
    service = WikiService(client, ["Team"], True, False, False)

    result = await service.search("q")

    assert [item.slug for item in result.results] == ["Team/Page"]


def test_enabled_wiki_service_rejects_empty_roots() -> None:
    with pytest.raises(InvalidPath):
        WikiService(AsyncMock(), [], True, False, False)

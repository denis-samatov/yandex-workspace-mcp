from unittest.mock import AsyncMock

import pytest

from yandex_workspace_mcp.models.errors import InvalidPath
from yandex_workspace_mcp.models.wiki import (
    GridGetInput,
    PageListInput,
    PageLocator,
    WikiGrid,
    WikiGridPage,
    WikiPage,
)
from yandex_workspace_mcp.services.wiki import WikiService


def _service(client: AsyncMock) -> WikiService:
    return WikiService(
        client=client,
        allowed_roots=["/Team"],
        can_read=True,
        can_write=True,
        can_delete=True,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("locator", "resolved_slug"),
    [
        (PageLocator(slug="Team/Page"), "Team/Page"),
        (PageLocator(page_id=42), "Team/Page"),
        (PageLocator(url="https://wiki.yandex.ru/Team/Page"), "Team/Page"),
    ],
)
async def test_page_locator_is_resolved_then_root_authorized(locator, resolved_slug) -> None:
    client = AsyncMock()
    client.get_page.return_value = WikiPage(id=42, slug=resolved_slug)
    service = _service(client)

    authorized = await service.resolve_page(locator)

    assert authorized.page.id == 42
    assert authorized.normalized_slug == resolved_slug
    client.get_page.assert_awaited_once_with(locator, credentials=None)


@pytest.mark.asyncio
async def test_page_id_resolving_outside_root_is_rejected() -> None:
    client = AsyncMock()
    client.get_page.return_value = WikiPage(id=9, slug="Other/Secret", content="secret")
    service = _service(client)

    with pytest.raises(InvalidPath):
        await service.resolve_page(PageLocator(page_id=9))


@pytest.mark.asyncio
async def test_grid_id_owner_is_resolved_and_outside_root_is_rejected() -> None:
    client = AsyncMock()
    client.get_grid.return_value = WikiGrid(id="g", page=WikiGridPage(id=9, slug="Other/Secret"))
    client.get_page.return_value = WikiPage(id=9, slug="Other/Secret", content="secret")
    service = _service(client)

    with pytest.raises(InvalidPath):
        await service.resolve_grid_owner("g")

    client.get_grid.assert_awaited_once_with(GridGetInput(grid_id="g"), credentials=None)
    client.get_page.assert_awaited_once_with(PageLocator(page_id=9), credentials=None)


@pytest.mark.parametrize(
    ("slug", "allowed"),
    [("Team/New", True), ("/Team/New", True), ("Teamwork/New", False), ("Other/New", False)],
)
def test_destination_segment_boundaries(slug: str, allowed: bool) -> None:
    service = _service(AsyncMock())
    if allowed:
        assert service.authorize_destination(slug) == "Team/New"
    else:
        with pytest.raises(InvalidPath):
            service.authorize_destination(slug)


@pytest.mark.asyncio
async def test_page_collection_body_is_not_returned_or_requested_after_failed_authorization() -> (
    None
):
    client = AsyncMock()
    client.get_page.return_value = WikiPage(id=9, slug="Other/Secret", content="secret")
    service = _service(client)

    with pytest.raises(InvalidPath):
        await service.get_comments(PageListInput(locator=PageLocator(page_id=9)))

    client.get_comments.assert_not_awaited()


@pytest.mark.asyncio
async def test_grid_read_uses_authorized_owner_before_returning_grid() -> None:
    client = AsyncMock()
    grid = WikiGrid(id="g", page=WikiGridPage(id=42, slug="Team/Page"))
    client.get_grid.return_value = grid
    client.get_page.return_value = WikiPage(id=42, slug="Team/Page")
    service = _service(client)

    result = await service.get_grid(GridGetInput(grid_id="g", revision=3))

    assert result == grid
    assert client.get_grid.await_count == 2

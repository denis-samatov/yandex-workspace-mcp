import asyncio
from unittest.mock import AsyncMock

import pytest

from yandex_workspace_mcp.clients.wiki import SearchFilterUnsupported, SearchUnavailable
from yandex_workspace_mcp.models.errors import PermissionDenied, RateLimitExceeded
from yandex_workspace_mcp.models.wiki import (
    DescendantItem,
    DescendantsResponse,
    WikiSearchItem,
    WikiSearchResponse,
)
from yandex_workspace_mcp.services.wiki import WikiService


def _item(slug: str, *, page_id: int = 1) -> WikiSearchItem:
    return WikiSearchItem(id=page_id, slug=slug, title=slug, type="page")


def _service(client: AsyncMock, roots: list[str]) -> WikiService:
    return WikiService(
        client=client,
        allowed_roots=roots,
        can_read=True,
        can_write=False,
        can_delete=False,
    )


@pytest.mark.asyncio
async def test_search_post_filters_segment_boundaries_and_deduplicates_roots() -> None:
    client = AsyncMock()

    async def search(_input, *, cluster=None, credentials=None):
        if cluster == "Work":
            return WikiSearchResponse(
                results=[_item("Work/Page", page_id=1), _item("Workshop/Leak", page_id=2)]
            )
        return WikiSearchResponse(
            results=[_item("Work/Page", page_id=1), _item("Work/Sub/Page", page_id=3)]
        )

    client.search.side_effect = search
    service = _service(client, ["Work", "Work/Sub"])

    result = await service.search("page", limit=10)

    assert [item.slug for item in result.results] == ["Work/Page", "Work/Sub/Page"]
    assert all(item.slug != "Workshop/Leak" for item in result.results)


@pytest.mark.asyncio
async def test_root_slash_uses_one_unfiltered_search() -> None:
    client = AsyncMock()
    client.search.return_value = WikiSearchResponse(results=[_item("Any/Page")])
    service = _service(client, ["/"])

    result = await service.search("page", limit=10)

    assert [item.slug for item in result.results] == ["Any/Page"]
    assert client.search.await_args.kwargs["cluster"] is None
    assert client.search.await_count == 1


@pytest.mark.asyncio
async def test_filter_drift_retries_once_globally_and_marks_truncation() -> None:
    client = AsyncMock()
    client.search.side_effect = [
        SearchFilterUnsupported(),
        WikiSearchResponse(
            results=[_item("Other/Leak", page_id=index) for index in range(1, 50)]
            + [_item("Work/Allowed", page_id=50)]
        ),
    ]
    service = _service(client, ["Work"])

    result = await service.search("page", limit=20)

    assert [item.slug for item in result.results] == ["Work/Allowed"]
    assert result.truncated_by_upstream is True
    assert client.search.await_count == 2
    assert client.search.await_args_list[1].kwargs["cluster"] is None


@pytest.mark.asyncio
async def test_endpoint_unavailable_uses_bounded_descendants_fallback() -> None:
    client = AsyncMock()
    client.search.side_effect = SearchUnavailable()
    client.get_descendants.side_effect = [
        DescendantsResponse(
            results=[
                DescendantItem(id=1, slug="Work/Needle"),
                DescendantItem(id=2, slug="Work/Other"),
            ],
            next_cursor="next",
        ),
        DescendantsResponse(
            results=[DescendantItem(id=3, slug="Work/Needle/Child")],
            next_cursor=None,
        ),
    ]
    service = _service(client, ["Work"])

    result = await service.search("needle", limit=10)

    assert [item.slug for item in result.results] == [
        "Work/Needle",
        "Work/Needle/Child",
    ]
    assert result.degraded is True
    assert result.search_mode == "descendants"
    assert client.get_descendants.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [PermissionDenied(), RateLimitExceeded()])
async def test_policy_and_rate_failures_never_fallback(failure: Exception) -> None:
    client = AsyncMock()
    client.search.side_effect = failure
    service = _service(client, ["Work"])

    with pytest.raises(type(failure)):
        await service.search("q")

    client.get_descendants.assert_not_awaited()


@pytest.mark.asyncio
async def test_empty_full_text_results_do_not_fallback() -> None:
    client = AsyncMock()
    client.search.return_value = WikiSearchResponse()
    service = _service(client, ["Work"])

    assert (await service.search("q")).results == []
    client.get_descendants.assert_not_awaited()


@pytest.mark.asyncio
async def test_cluster_search_concurrency_is_capped_at_four() -> None:
    client = AsyncMock()
    active = 0
    peak = 0

    async def search(_input, *, cluster=None, credentials=None):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        active -= 1
        return WikiSearchResponse(results=[_item(f"{cluster}/Page")])

    client.search.side_effect = search
    service = _service(client, [f"Root{index}" for index in range(10)])

    await service.search("q", limit=50)

    assert peak <= 4

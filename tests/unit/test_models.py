import importlib
import importlib.util

import pytest
from pydantic import ValidationError


def test_increment_one_model_modules_exist() -> None:
    common = importlib.import_module("yandex_workspace_mcp.models.common")

    assert importlib.util.find_spec("yandex_workspace_mcp.models.wiki") is not None
    assert importlib.util.find_spec("yandex_workspace_mcp.models.disk") is not None
    assert hasattr(common, "SourceStatus")


def test_public_inputs_are_strict_and_forbid_unknown_fields() -> None:
    WikiSearchInput = importlib.import_module("yandex_workspace_mcp.models.wiki").WikiSearchInput

    with pytest.raises(ValidationError):
        WikiSearchInput(query="term", surprise=True)

    with pytest.raises(ValidationError):
        WikiSearchInput(query=123)


def test_wiki_search_legacy_page_and_reserved_cursor_contract() -> None:
    WikiSearchInput = importlib.import_module("yandex_workspace_mcp.models.wiki").WikiSearchInput

    assert WikiSearchInput(query="term", page=6).page == 6

    with pytest.raises(ValidationError):
        WikiSearchInput(query="term", page=0)

    with pytest.raises(ValidationError):
        WikiSearchInput(query="term", cursor="not-supported")


def test_unknown_wiki_wire_fields_are_not_exposed_publicly() -> None:
    wiki_models = importlib.import_module("yandex_workspace_mcp.models.wiki")
    WikiSearchWire = wiki_models.WikiSearchWire
    map_wiki_search = wiki_models.map_wiki_search

    wire = WikiSearchWire.model_validate(
        {
            "results": [
                {
                    "id": 7,
                    "slug": "team/page",
                    "title": "Page",
                    "content": "matching excerpt",
                    "type": "page",
                    "new_item_field": "hidden",
                }
            ],
            "new_envelope_field": "hidden",
        }
    )

    public = map_wiki_search(wire)

    assert public.results[0].content_excerpt == "matching excerpt"
    assert public.truncated_by_upstream is False
    assert public.degraded is False
    assert public.search_mode == "full_text"
    assert "new_item_field" not in public.model_dump_json()
    assert "new_envelope_field" not in public.model_dump_json()


def test_unknown_disk_wire_fields_are_not_exposed_publicly() -> None:
    disk_models = importlib.import_module("yandex_workspace_mcp.models.disk")
    DiskResourceWire = disk_models.DiskResourceWire
    map_disk_resource = disk_models.map_disk_resource

    wire = DiskResourceWire.model_validate(
        {
            "path": "disk:/Work/report.md",
            "name": "report.md",
            "type": "file",
            "size": 12,
            "file": "https://signed.example/secret?token=x",
            "new_upstream_field": "hidden",
        }
    )

    public = map_disk_resource(wire)

    assert public.path == "/Work/report.md"
    assert public.name == "report.md"
    assert "file" not in public.model_dump()
    assert "new_upstream_field" not in public.model_dump_json()


def test_search_result_additions_default_without_breaking_existing_fields() -> None:
    common = importlib.import_module("yandex_workspace_mcp.models.common")
    SearchResult = common.SearchResult
    SourceStatus = common.SourceStatus

    result = SearchResult(results=[])

    assert result.results == []
    assert result.next_cursor is None
    assert result.partial_failures == {}
    assert result.sources == {}

    status = SourceStatus(state="degraded", search_mode="descendants")
    assert status.state == "degraded"

import importlib
import json
import math
from pathlib import Path

import pytest
from pydantic import ValidationError


@pytest.fixture(scope="module")
def wiki():
    return importlib.import_module("yandex_workspace_mcp.models.wiki")


def test_normative_wiki_models_exist(wiki) -> None:
    names = {
        "PageLocatorInput",
        "PageDeleteInput",
        "PageListInput",
        "PageResourceListInput",
        "GridGetInput",
        "PageCreateInput",
        "PageUpdateInput",
        "PageAppendInput",
        "PageCloneInput",
        "CommentCreateInput",
        "PageRecoverInput",
        "WikiAttachmentUploadInput",
        "GridCreateInput",
        "GridUpdateInput",
        "GridCopyInput",
        "GridDeleteInput",
        "GridRowsAddInput",
        "GridCellsUpdateInput",
        "GridRowsDeleteInput",
        "GridRowMoveInput",
        "GridColumnsAddInput",
        "GridColumnsDeleteInput",
        "GridColumnMoveInput",
        "CommentsResponse",
        "AttachmentsResponse",
        "ResourcesResponse",
        "GridsResponse",
        "WikiGrid",
        "GridCellsResponse",
        "GridMutationResponse",
    }
    assert not (names - vars(wiki).keys())


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"page_id": 1, "slug": "team"},
        {"url": "https://wiki.yandex.ru/team", "slug": "team"},
        {"page_id": 0},
        {"slug": "team", "unknown": True},
    ],
)
def test_page_locator_is_exactly_one_strict_field(wiki, payload) -> None:
    with pytest.raises(ValidationError):
        wiki.PageLocator(**payload)


def test_page_mutation_cross_field_rules(wiki) -> None:
    locator = wiki.PageLocator(slug="team")
    with pytest.raises(ValidationError):
        wiki.PageUpdateInput(locator=locator)
    with pytest.raises(ValidationError):
        wiki.PageAppendInput(locator=locator, content="x", location="top", anchor="section")
    assert wiki.PageUpdateInput(locator=locator, content="").content == ""
    assert wiki.PageAppendInput(locator=locator, content="x").location == "bottom"


def test_grid_row_and_cell_locator_xor_rules(wiki) -> None:
    with pytest.raises(ValidationError):
        wiki.GridRowsAddInput(
            grid_id="g", revision=1, rows=[{"a": 1}], position=0, after_row_id="r"
        )
    with pytest.raises(ValidationError):
        wiki.GridRowMoveInput(grid_id="g", revision=1, row_id="r")
    with pytest.raises(ValidationError):
        wiki.GridCellUpdate(row_id="r", value=1)
    with pytest.raises(ValidationError):
        wiki.GridCellUpdate(row_id="r", column_id="c", column_slug="s", value=1)
    assert wiki.GridCellUpdate(row_id="r", column_slug="s", value=None).value is None


def test_grid_column_type_specific_rules_and_unique_slugs(wiki) -> None:
    with pytest.raises(ValidationError):
        wiki.GridColumnCreate(title="A", slug="a", type="select", required=True)
    with pytest.raises(ValidationError):
        wiki.GridColumnCreate(
            title="A", slug="a", type="string", required=True, select_options=["x"]
        )
    with pytest.raises(ValidationError):
        wiki.GridColumnCreate(title="A", slug="a", type="number", required=True, multiple=True)
    with pytest.raises(ValidationError):
        wiki.GridColumnsAddInput(
            grid_id="g",
            revision=1,
            columns=[
                {"title": "A", "slug": "same", "type": "string", "required": True},
                {"title": "B", "slug": "same", "type": "staff", "required": False},
            ],
        )
    column = wiki.GridColumnCreate(
        title="People", slug="people", type="staff", required=False, multiple=True
    )
    assert column.multiple is True


def test_bounds_duplicates_scalars_and_unknown_fields(wiki) -> None:
    with pytest.raises(ValidationError):
        wiki.PageListInput(locator={"slug": "team"}, page_size=101)
    with pytest.raises(ValidationError):
        wiki.GridRowsDeleteInput(grid_id="g", revision=0, row_ids=["r", "r"])
    with pytest.raises(ValidationError):
        wiki.GridRowsAddInput(grid_id="g", revision=0, rows=[{"x": {"nested": True}}])
    with pytest.raises(ValidationError):
        wiki.GridRowsAddInput(grid_id="g", revision=0, rows=[{"x": math.inf}])
    with pytest.raises(ValidationError):
        wiki.GridGetInput(grid_id="g", surprise=True)


def test_public_wire_mapping_discards_unknowns_and_download_urls(wiki) -> None:
    wire = wiki.AttachmentsWire.model_validate(
        {
            "results": [
                {
                    "id": 7,
                    "name": "report.pdf",
                    "download_url": "https://signed.example/secret",
                    "new_upstream_field": "ignored",
                }
            ],
            "new_envelope_field": True,
        }
    )
    public = wiki.map_attachments(wire)
    assert public.model_dump() == {
        "results": [
            {
                "id": 7,
                "name": "report.pdf",
                "size": None,
                "description": None,
                "mime_type": None,
                "created_at": None,
                "has_preview": None,
                "check_status": None,
                "is_downloadable": None,
                "user": None,
            }
        ],
        "next_cursor": None,
        "prev_cursor": None,
        "truncated": False,
    }


def test_cells_and_mutation_responses_have_distinct_envelopes(wiki) -> None:
    cells_schema = wiki.GridCellsResponse.model_json_schema()["properties"]
    mutation_schema = wiki.GridMutationResponse.model_json_schema()["properties"]
    assert "cells" in cells_schema and "results" not in cells_schema
    assert "results" in mutation_schema and "cells" not in mutation_schema


def test_wiki_model_schema_snapshot_matches_generator(wiki) -> None:
    snapshot = json.loads(
        Path("tests/snapshots/wiki_tool_schemas.json").read_text(encoding="utf-8")
    )
    expected = {name: getattr(wiki, name).model_json_schema() for name in snapshot}
    assert snapshot == expected

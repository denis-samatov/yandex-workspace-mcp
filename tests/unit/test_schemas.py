import importlib

import pytest


@pytest.fixture(autouse=True)
def setup_env_and_reload(monkeypatch):
    monkeypatch.setenv("YANDEX_OAUTH_TOKEN", "fake")
    monkeypatch.setenv("DISK_WRITE", "true")
    monkeypatch.setenv("WIKI_WRITE", "true")
    monkeypatch.setenv("DISK_DELETE", "true")

    import yandex_workspace_mcp.config
    import yandex_workspace_mcp.server

    importlib.reload(yandex_workspace_mcp.config)
    importlib.reload(yandex_workspace_mcp.server)

    yield yandex_workspace_mcp.server.mcp_server


@pytest.mark.asyncio
async def test_tools_registration(setup_env_and_reload):
    mcp_server = setup_env_and_reload
    tools = await mcp_server.list_tools()
    tool_names = [t.name for t in tools]

    expected_tools = {
        "search",
        "fetch",
        "disk_list",
        "disk_get_metadata",
        "disk_read",
        "disk_upload",
        "disk_create_folder",
        "disk_copy",
        "disk_move",
        "disk_delete",
        "wiki_search",
        "wiki_get_page",
        "wiki_get_tree",
        "wiki_create_page",
        "wiki_update_page",
    }

    for ext in expected_tools:
        assert ext in tool_names


@pytest.mark.asyncio
async def test_tools_schema_validity(setup_env_and_reload):
    mcp_server = setup_env_and_reload
    tools = await mcp_server.list_tools()

    for tool in tools:
        schema = tool.inputSchema if hasattr(tool, "inputSchema") else tool.input_schema
        assert isinstance(schema, dict)
        assert schema.get("type") == "object"
        assert "properties" in schema

        # Test tool annotations
        if tool.name == "disk_read":
            assert tool.annotations is not None
            assert tool.annotations.read_only_hint is True


@pytest.mark.asyncio
async def test_legacy_wiki_tool_schemas_remain_flattened(setup_env_and_reload):
    tools = {tool.name: tool for tool in await setup_env_and_reload.list_tools()}

    assert tools["wiki_search"].input_schema == {
        "properties": {
            "query": {"title": "Query", "type": "string"},
            "limit": {
                "default": 50,
                "maximum": 50,
                "minimum": 1,
                "title": "Limit",
                "type": "integer",
            },
            "page": {"default": 1, "minimum": 1, "title": "Page", "type": "integer"},
            "cursor": {"default": None, "title": "Cursor", "type": "null"},
        },
        "required": ["query"],
        "title": "wiki_searchArguments",
        "type": "object",
    }
    for name in ("wiki_get_page", "wiki_get_tree"):
        assert tools[name].input_schema["properties"] == {
            "slug": {"title": "Slug", "type": "string"}
        }
        assert tools[name].input_schema["required"] == ["slug"]
    assert tools["wiki_create_page"].input_schema["required"] == ["slug", "title", "body"]
    assert list(tools["wiki_create_page"].input_schema["properties"]) == [
        "slug",
        "title",
        "body",
    ]
    assert tools["wiki_update_page"].input_schema["required"] == ["slug", "body"]
    assert tools["wiki_update_page"].input_schema["properties"]["title"]["default"] is None


@pytest.mark.asyncio
async def test_new_wiki_tools_expose_normative_top_level_fields(setup_env_and_reload):
    tools = {tool.name: tool for tool in await setup_env_and_reload.list_tools()}
    expected = {
        "wiki_get_descendants": {"locator", "include_self", "page_size", "cursor"},
        "wiki_get_grid": {"grid_id", "revision", "row_ids", "column_slugs"},
        "wiki_append_page": {"locator", "content", "location", "anchor"},
        "wiki_copy_grid": {"grid_id", "destination", "title"},
        "wiki_update_grid_cells": {"grid_id", "revision", "cells"},
    }
    for name, fields in expected.items():
        assert set(tools[name].input_schema["properties"]) == fields
        assert "input" not in tools[name].input_schema["properties"]


@pytest.mark.asyncio
async def test_disk_tools_expose_normative_flattened_fields(setup_env_and_reload):
    tools = {tool.name: tool for tool in await setup_env_and_reload.list_tools()}
    expected = {
        "disk_list": {"path", "limit", "offset", "sort"},
        "disk_recent": {"limit", "media_type"},
        "disk_search": {"query", "limit", "cursor", "media_type"},
        "disk_copy": {"from_path", "to_path", "overwrite"},
        "disk_move": {"from_path", "to_path", "overwrite"},
        "disk_rename": {"path", "new_name", "overwrite"},
        "disk_delete": {"path", "permanently"},
        "disk_restore_from_trash": {"trash_path", "destination_path", "overwrite"},
    }
    for name, fields in expected.items():
        assert set(tools[name].input_schema["properties"]) == fields
        assert "input" not in tools[name].input_schema["properties"]

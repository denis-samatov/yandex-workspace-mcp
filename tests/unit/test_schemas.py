import importlib
import os

import pytest


@pytest.fixture(autouse=True)
def setup_env_and_reload():
    os.environ["YANDEX_OAUTH_TOKEN"] = "fake"
    os.environ["DISK_WRITE"] = "true"
    os.environ["WIKI_WRITE"] = "true"
    os.environ["DISK_DELETE"] = "true"
    
    import yandex_workspace_mcp.config
    import yandex_workspace_mcp.server
    importlib.reload(yandex_workspace_mcp.config)
    importlib.reload(yandex_workspace_mcp.server)
    
    yield yandex_workspace_mcp.server.mcp_server
    
    del os.environ["YANDEX_OAUTH_TOKEN"]

@pytest.mark.asyncio
async def test_tools_registration(setup_env_and_reload):
    mcp_server = setup_env_and_reload
    tools = await mcp_server.list_tools()
    tool_names = [t.name for t in tools]
    
    expected_tools = {
        'search', 'fetch', 
        'disk_list', 'disk_get_metadata', 'disk_read', 
        'disk_upload', 'disk_create_folder', 'disk_copy', 'disk_move', 'disk_delete',
        'wiki_search', 'wiki_get_page', 'wiki_get_tree', 
        'wiki_create_page', 'wiki_update_page'
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


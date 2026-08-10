import pytest
from yandex_workspace_mcp.security.paths import normalize_path, is_path_in_allowed_roots
from yandex_workspace_mcp.exceptions import InvalidPath

def test_normalize_path():
    assert normalize_path("/Work") == "/Work"
    assert normalize_path("Work") == "/Work"
    assert normalize_path("disk:/Work") == "/Work"

def test_normalize_path_traversal():
    with pytest.raises(InvalidPath):
        normalize_path("/Work/../../Personal")

def test_is_path_in_allowed_roots():
    roots = ["/Work", "/Research"]
    assert is_path_in_allowed_roots("/Work/report.md", roots) is True
    assert is_path_in_allowed_roots("/Research", roots) is True
    assert is_path_in_allowed_roots("/Personal/photo.jpg", roots) is False
    assert is_path_in_allowed_roots("/", roots) is False
    
def test_is_path_in_allowed_roots_empty():
    # If no allowed roots are set, it should allow all
    assert is_path_in_allowed_roots("/Work/report.md", []) is True

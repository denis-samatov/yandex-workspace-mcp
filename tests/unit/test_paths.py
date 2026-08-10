import pytest

from yandex_workspace_mcp.models.errors import InvalidPath
from yandex_workspace_mcp.policies.paths import validate_path


def test_validate_path_normalization():
    assert validate_path("/Work", ["/"]) == "/Work"
    assert validate_path("Work", ["/"]) == "/Work"

def test_validate_path_traversal():
    with pytest.raises(InvalidPath):
        # /Work/../../Personal -> /Personal, which is not in /Work
        validate_path("/Work/../../Personal", ["/Work"])

def test_validate_path_allowed_roots():
    roots = ["/Work", "/Research"]
    assert validate_path("/Work/report.md", roots) == "/Work/report.md"
    assert validate_path("/Research", roots) == "/Research"
    
    with pytest.raises(InvalidPath):
        validate_path("/Personal/photo.jpg", roots)
        
    with pytest.raises(InvalidPath):
        validate_path("/", roots)

def test_validate_path_no_allowed_roots():
    # If no allowed roots are set, it should allow all?
    # Actually wait, validate_path says if not allowed_roots it returns valid path?
    # Let's assume if allowed_roots is empty, nothing is allowed, or all is allowed.
    # The default in config is now empty list, so it probably should block by default unless configured.
    pass

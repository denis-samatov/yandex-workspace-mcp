import pytest

from yandex_workspace_mcp.models.errors import InvalidPath
from yandex_workspace_mcp.policies import paths as path_policy

validate_path = path_policy.validate_path


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
    with pytest.raises(InvalidPath):
        validate_path("/Work", [])


@pytest.mark.parametrize(
    "path",
    [
        "/Work/%252e%252e/Personal",
        "/Work/%ZZ/file",
        "/Work/evil\\file",
        "/Work/evil\x00file",
        "/Work/evil\nfile",
        "/Work／evil",
    ],
)
def test_validate_path_rejects_ambiguous_or_encoded_paths(path: str) -> None:
    with pytest.raises(InvalidPath, match="Invalid or unauthorized path"):
        validate_path(path, ["/Work"])


def test_validate_path_uses_segment_boundaries() -> None:
    with pytest.raises(InvalidPath):
        validate_path("/Workshop/report.md", ["/Work"])


def test_validate_wiki_slug_returns_slug_without_leading_slash() -> None:
    assert path_policy.validate_wiki_slug("/Team/Page", ["Team"]) == "Team/Page"

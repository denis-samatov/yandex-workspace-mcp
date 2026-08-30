import pytest

from yandex_workspace_mcp.models.errors import InvalidInput
from yandex_workspace_mcp.policies.urls import validate_disk_operation_url


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            "/v1/disk/operations/abc",
            "https://cloud-api.yandex.net/v1/disk/operations/abc",
        ),
        (
            "https://cloud-api.yandex.net/v1/disk/operations/abc?fields=status",
            "https://cloud-api.yandex.net/v1/disk/operations/abc?fields=status",
        ),
    ],
)
def test_disk_operation_url_accepts_only_relative_or_exact_origin(
    value: str, expected: str
) -> None:
    assert validate_disk_operation_url(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "http://cloud-api.yandex.net/v1/disk/operations/x",
        "https://evil.example/v1/disk/operations/x",
        "https://cloud-api.yandex.net.evil.example/v1/disk/operations/x",
        "https://u:p@cloud-api.yandex.net/v1/disk/operations/x",
        "https://cloud-api.yandex.net:444/v1/disk/operations/x",
        "https://cloud-api.yandex.net/v1/disk/operations/x#fragment",
        "//evil.example/v1/disk/operations/x",
        "/v1/operations/wiki-only",
    ],
)
def test_disk_operation_url_rejects_other_targets(value: str) -> None:
    with pytest.raises(InvalidInput):
        validate_disk_operation_url(value)

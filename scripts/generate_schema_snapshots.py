import json
from pathlib import Path

from yandex_workspace_mcp.models import disk, wiki

WIKI_INPUT_MODELS = (
    "WikiSearchInput",
    "PageLocatorInput",
    "DescendantsInput",
    "PageListInput",
    "PageResourceListInput",
    "GridGetInput",
    "PageCreateInput",
    "PageUpdateInput",
    "PageAppendInput",
    "PageCloneInput",
    "CommentCreateInput",
    "PageDeleteInput",
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
)

DISK_MODELS = (
    "DiskListInput",
    "DiskRecentInput",
    "DiskSearchInput",
    "DiskPathInput",
    "DiskDeleteInput",
    "DiskCopyInput",
    "DiskMoveInput",
    "DiskRenameInput",
    "DiskLocalUploadInput",
    "UploadJobIDInput",
    "UploadJobListInput",
    "DiskURLUploadInput",
    "DiskPublicResourceInput",
    "DiskTrashListInput",
    "DiskTrashRestoreInput",
    "DiskTrashEmptyInput",
    "DiskInfo",
    "DiskResource",
    "DiskPublicResource",
    "DiskResourcePage",
    "DiskSearchResponse",
    "DiskOperationResponse",
    "DiskLinkResponse",
    "UploadJobResponse",
    "UploadJobListResponse",
)


def main() -> None:
    output = Path("tests/snapshots/wiki_tool_schemas.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    schemas = {name: getattr(wiki, name).model_json_schema() for name in WIKI_INPUT_MODELS}
    output.write_text(
        json.dumps(schemas, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    disk_output = Path("tests/snapshots/disk_tool_schemas.json")
    disk_schemas = {name: getattr(disk, name).model_json_schema() for name in DISK_MODELS}
    disk_output.write_text(
        json.dumps(disk_schemas, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

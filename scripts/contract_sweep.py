"""Explicit live drift sweep for the typed Wiki and Disk contracts."""

import argparse
import asyncio
import json
import logging
import tempfile
import uuid
from collections.abc import Awaitable
from pathlib import Path
from typing import Any

from yandex_workspace_mcp.clients.disk import YandexDiskClient
from yandex_workspace_mcp.clients.signed import SignedTransferClient
from yandex_workspace_mcp.clients.wiki import YandexWikiClient
from yandex_workspace_mcp.config import get_settings
from yandex_workspace_mcp.models.wiki import (
    CommentCreateInput,
    DescendantsInput,
    GridCellsUpdateInput,
    GridCellUpdate,
    GridColumnCreate,
    GridColumnMoveInput,
    GridColumnsAddInput,
    GridColumnsDeleteInput,
    GridCreateInput,
    GridDeleteInput,
    GridGetInput,
    GridRowMoveInput,
    GridRowsAddInput,
    GridRowsDeleteInput,
    GridUpdateInput,
    PageAppendInput,
    PageCloneInput,
    PageCreateInput,
    PageListInput,
    PageLocator,
    PageResourceListInput,
    PageUpdateInput,
    WikiAttachmentUploadInput,
    WikiSearchInput,
)
from yandex_workspace_mcp.policies.cursors import CursorCodec
from yandex_workspace_mcp.policies.local_files import open_allowed_local_file
from yandex_workspace_mcp.services.disk import DiskService

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run explicit live Yandex Wiki/Disk contract checks on scratch roots."
    )
    parser.add_argument("--acknowledge-live", action="store_true")
    parser.add_argument("--wiki-scratch-root", required=True)
    parser.add_argument("--disk-scratch-root", required=True)
    parser.add_argument("--query", default="contract-sweep")
    parser.add_argument("--report", type=Path)
    return parser


def _revision(value: str | None) -> int:
    if value is None or not value.isdecimal():
        raise RuntimeError("observed Wiki grid revision is not a decimal integer")
    return int(value)


async def _observe[T](
    name: str,
    awaitable: Awaitable[T],
    observations: list[dict[str, Any]],
) -> T:
    try:
        result = await awaitable
    except Exception as exc:
        observations.append({"operation": name, "status": "drift", "error": type(exc).__name__})
        raise
    observations.append({"operation": name, "status": "ok", "response_type": type(result).__name__})
    return result


def _is_service_root(value: str) -> bool:
    normalized = value.strip().casefold().rstrip("/")
    return normalized in {"", "disk:"}


async def _wiki_sweep(
    client: YandexWikiClient,
    signed_client: SignedTransferClient,
    *,
    scratch_root: str,
    query: str,
) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    cleanup_page_ids: list[int] = []
    run_id = uuid.uuid4().hex
    root = scratch_root.strip("/")
    source_slug = f"{root}/contract-sweep-{run_id}"
    destination_slug = f"{root}/contract-sweep-destination-{run_id}"
    clone_slug = f"{root}/contract-sweep-clone-{run_id}"
    try:
        source = await _observe(
            "create_page",
            client.create_page(
                PageCreateInput(slug=source_slug, title="Contract sweep", content="seed")
            ),
            observations,
        )
        cleanup_page_ids.append(source.id)
        destination = await _observe(
            "create_destination_page",
            client.create_page(
                PageCreateInput(slug=destination_slug, title="Destination", content="seed")
            ),
            observations,
        )
        cleanup_page_ids.append(destination.id)
        source_locator = PageLocator(page_id=source.id)

        await _observe("search", client.search(WikiSearchInput(query=query, limit=5)), observations)
        await _observe("get_page", client.get_page(source_locator), observations)
        await _observe(
            "get_descendants",
            client.get_descendants(DescendantsInput(locator=source_locator)),
            observations,
        )
        await _observe(
            "update_page",
            client.update_page(
                source.id,
                PageUpdateInput(locator=source_locator, title="Contract sweep updated"),
            ),
            observations,
        )
        await _observe(
            "append_page",
            client.append_page(
                source.id,
                PageAppendInput(locator=source_locator, content="\nappended"),
            ),
            observations,
        )
        await _observe(
            "add_comment",
            client.add_comment(
                source.id,
                CommentCreateInput(locator=source_locator, body="contract sweep"),
            ),
            observations,
        )
        clone = await _observe(
            "clone_page",
            client.clone_page(
                source.id,
                PageCloneInput(source=source_locator, destination_slug=clone_slug),
            ),
            observations,
        )
        cleanup_page_ids.append(clone.id)

        grid = await _observe(
            "create_grid",
            client.create_grid(
                source.id,
                GridCreateInput(locator=source_locator, title="Contract grid"),
            ),
            observations,
        )
        grid_id = str(grid.id)
        updated = await _observe(
            "update_grid",
            client.update_grid(
                GridUpdateInput(
                    grid_id=grid_id,
                    revision=_revision(grid.revision),
                    title="Contract grid updated",
                )
            ),
            observations,
        )
        revision = _revision(updated.grid.revision)
        columns = await _observe(
            "add_grid_columns",
            client.add_grid_columns(
                GridColumnsAddInput(
                    grid_id=grid_id,
                    revision=revision,
                    columns=[
                        GridColumnCreate(title="Name", slug="name", type="string", required=True),
                        GridColumnCreate(title="Rank", slug="rank", type="number", required=False),
                    ],
                )
            ),
            observations,
        )
        rows = await _observe(
            "add_grid_rows",
            client.add_grid_rows(
                GridRowsAddInput(
                    grid_id=grid_id,
                    revision=_revision(columns.revision),
                    rows=[{"name": "one", "rank": 1}, {"name": "two", "rank": 2}],
                )
            ),
            observations,
        )
        row_ids = [str(row.id) for row in rows.results if row.id is not None]
        if len(row_ids) < 2:
            raise RuntimeError("add_grid_rows did not return two row IDs")
        cells = await _observe(
            "update_grid_cells",
            client.update_grid_cells(
                GridCellsUpdateInput(
                    grid_id=grid_id,
                    revision=_revision(rows.revision),
                    cells=[GridCellUpdate(row_id=row_ids[0], column_slug="name", value="updated")],
                )
            ),
            observations,
        )
        moved_row = await _observe(
            "move_grid_row",
            client.move_grid_row(
                GridRowMoveInput(
                    grid_id=grid_id,
                    revision=_revision(cells.revision),
                    row_id=row_ids[1],
                    position=0,
                )
            ),
            observations,
        )
        moved_column = await _observe(
            "move_grid_column",
            client.move_grid_column(
                GridColumnMoveInput(
                    grid_id=grid_id,
                    revision=_revision(moved_row.revision),
                    column_slug="rank",
                    position=0,
                )
            ),
            observations,
        )
        deleted_rows = await _observe(
            "delete_grid_rows",
            client.delete_grid_rows(
                GridRowsDeleteInput(
                    grid_id=grid_id,
                    revision=_revision(moved_column.revision),
                    row_ids=[row_ids[1]],
                )
            ),
            observations,
        )
        deleted_columns = await _observe(
            "delete_grid_columns",
            client.delete_grid_columns(
                GridColumnsDeleteInput(
                    grid_id=grid_id,
                    revision=_revision(deleted_rows.revision),
                    column_slugs=["rank"],
                )
            ),
            observations,
        )
        await _observe(
            "get_grid",
            client.get_grid(
                GridGetInput(grid_id=grid_id, revision=_revision(deleted_columns.revision))
            ),
            observations,
        )
        await _observe(
            "copy_grid",
            client.copy_grid(grid_id, destination_slug=destination_slug, title="Grid copy"),
            observations,
        )

        common_list = PageListInput(locator=source_locator)
        await _observe("get_comments", client.get_comments(common_list), observations)
        await _observe("get_attachments", client.get_attachments(common_list), observations)
        await _observe("get_grids", client.get_grids(common_list), observations)
        await _observe(
            "get_resources",
            client.get_resources(PageResourceListInput(locator=source_locator)),
            observations,
        )

        with tempfile.TemporaryDirectory(prefix="yandex-contract-sweep-") as temp_dir:
            file_path = Path(temp_dir) / "attachment.txt"
            file_path.write_text("contract sweep", encoding="utf-8")
            opened = open_allowed_local_file(str(file_path), [temp_dir], max_bytes=1024)
            try:
                await _observe(
                    "upload_attachment",
                    client.upload_attachment(
                        source.id,
                        opened,
                        WikiAttachmentUploadInput(
                            locator=source_locator,
                            file_path=str(file_path),
                        ),
                        signed_client=signed_client,
                    ),
                    observations,
                )
            finally:
                opened.close()

        await _observe(
            "delete_grid",
            client.delete_grid(GridDeleteInput(grid_id=grid_id)),
            observations,
        )
        recovery_token = await _observe("delete_page", client.delete_page(source.id), observations)
        recovered = await _observe(
            "recover_page", client.recover_page(recovery_token), observations
        )
        if recovered.id not in cleanup_page_ids:
            cleanup_page_ids.append(recovered.id)
    except Exception as exc:  # noqa: BLE001 -- retain drift and still finish cleanup
        observations.append(
            {"operation": "wiki_sweep", "status": "failed", "error": type(exc).__name__}
        )
    finally:
        for page_id in reversed(cleanup_page_ids):
            try:
                await client.delete_page(page_id)
            except Exception as exc:  # noqa: BLE001 -- cleanup must continue for all pages
                observations.append(
                    {
                        "operation": "cleanup_delete_page",
                        "status": "cleanup_failed",
                        "page_id": page_id,
                        "error": type(exc).__name__,
                    }
                )
                logger.warning(
                    "contract sweep cleanup failed for page_id=%s error=%s",
                    page_id,
                    type(exc).__name__,
                )
    return observations


async def _disk_sweep(
    client: YandexDiskClient,
    signed_client: SignedTransferClient,
    *,
    scratch_root: str,
    query: str,
) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    run_root = f"{scratch_root.rstrip('/')}/contract-sweep-{uuid.uuid4().hex}"
    note_path = f"{run_root}/contract-sweep-note.txt"
    try:
        with tempfile.TemporaryDirectory(prefix="yandex-disk-contract-sweep-") as temp_dir:
            local_file = Path(temp_dir) / "local-upload.txt"
            local_file.write_text("local contract sweep", encoding="utf-8")
            service = DiskService(
                client,
                [scratch_root],
                True,
                True,
                True,
                cursor_codec=CursorCodec((b"disk-contract-sweep-key-material!"[:32],)),
                upload_allowed_dirs=[temp_dir],
                max_upload_bytes=1024 * 1024,
                max_inline_text_bytes=1024 * 1024,
                signed_client=signed_client,
            )
            await _observe("disk_info", service.info(), observations)
            await _observe("disk_create_folder", service.create_folder(run_root), observations)
            await _observe(
                "disk_upload_inline",
                service.upload(note_path, "contract sweep", overwrite=True),
                observations,
            )
            local_destination = f"{run_root}/local-upload.txt"
            await _observe(
                "disk_upload_local_file",
                service.upload_local_file(
                    str(local_file),
                    local_destination,
                    overwrite=True,
                ),
                observations,
            )
            await _observe("disk_list", service.list_page(run_root), observations)
            await _observe("disk_recent", service.recent(limit=10), observations)
            await _observe(
                "disk_search",
                service.search(query, limit=5, principal="contract-sweep"),
                observations,
            )
            await _observe("disk_get_metadata", service.get_metadata(note_path), observations)
            await _observe(
                "disk_get_download_url",
                service.get_download_url(note_path),
                observations,
            )
            await _observe("disk_read", service.read_file(note_path), observations)

            copy_path = f"{run_root}/copy.txt"
            moved_path = f"{run_root}/moved.txt"
            renamed_path = f"{run_root}/renamed.txt"
            await _observe("disk_copy", service.copy(note_path, copy_path), observations)
            await _observe("disk_move", service.move(copy_path, moved_path), observations)
            await _observe(
                "disk_rename",
                service.rename(moved_path, "renamed.txt"),
                observations,
            )
            published = await _observe("disk_publish", service.publish(note_path), observations)
            if published.public_url:
                public_service = DiskService(
                    client,
                    [scratch_root],
                    True,
                    False,
                    False,
                    allowed_public_keys=[published.public_url],
                )
                await _observe(
                    "disk_get_public_resource",
                    public_service.get_public_resource(public_url=published.public_url),
                    observations,
                )
            else:
                observations.append(
                    {
                        "operation": "disk_get_public_resource",
                        "status": "not_run",
                        "reason": "publish metadata omitted public_url",
                    }
                )
            await _observe("disk_unpublish", service.unpublish(note_path), observations)

            await _observe(
                "disk_delete_to_trash",
                service.delete(renamed_path, permanently=False),
                observations,
            )
            trash = await _observe("disk_list_trash", client.list_trash(), observations)
            restored = next(
                (
                    entry
                    for entry in trash.items
                    if entry.origin_path == renamed_path and entry.resource.path is not None
                ),
                None,
            )
            if restored is not None:
                restored_path = restored.resource.path
                if restored_path is None:
                    raise RuntimeError("Trash resource omitted its restore path")
                await _observe(
                    "disk_restore_from_trash",
                    service.restore_from_trash(restored_path),
                    observations,
                )
            else:
                observations.append(
                    {
                        "operation": "disk_restore_from_trash",
                        "status": "not_run",
                        "reason": "deleted scratch entry not found in Trash page",
                    }
                )
            observations.extend(
                [
                    {
                        "operation": "disk_upload_from_url",
                        "status": "not_run",
                        "reason": "requires an explicit external URL fixture",
                    },
                    {
                        "operation": "disk_empty_trash",
                        "status": "not_run",
                        "reason": "global destructive operation is never part of a scratch sweep",
                    },
                ]
            )
    except Exception as exc:  # noqa: BLE001 -- retain drift and still finish cleanup
        observations.append(
            {"operation": "disk_sweep", "status": "failed", "error": type(exc).__name__}
        )
    finally:
        try:
            await client.delete_resource(run_root, permanently=True)
        except Exception as exc:  # noqa: BLE001 -- cleanup must remain best effort
            observations.append(
                {
                    "operation": "cleanup_delete_disk_root",
                    "status": "cleanup_failed",
                    "error": type(exc).__name__,
                }
            )
            logger.warning(
                "contract sweep Disk cleanup failed for root=%s error=%s",
                run_root,
                type(exc).__name__,
            )
    return observations


async def run(args: argparse.Namespace) -> dict[str, Any]:
    settings = get_settings()
    if not settings.yandex_oauth_token:
        raise SystemExit("YANDEX_OAUTH_TOKEN is required for the live sweep")
    token = settings.yandex_oauth_token.get_secret_value()
    wiki_client = YandexWikiClient(
        token=token,
        org_id=settings.yandex_wiki_org_id,
        is_cloud_org=settings.yandex_wiki_is_cloud_org,
    )
    disk_client = YandexDiskClient(token=token)
    signed_client = SignedTransferClient()
    try:
        results = await asyncio.gather(
            _wiki_sweep(
                wiki_client,
                signed_client,
                scratch_root=args.wiki_scratch_root,
                query=args.query,
            ),
            _disk_sweep(
                disk_client,
                signed_client,
                scratch_root=args.disk_scratch_root,
                query=args.query,
            ),
            return_exceptions=True,
        )
        observations: dict[str, list[dict[str, Any]]] = {}
        for name, result in zip(("wiki", "disk"), results, strict=True):
            if isinstance(result, BaseException):
                observations[name] = [
                    {
                        "operation": f"{name}_sweep",
                        "status": "failed",
                        "error": type(result).__name__,
                    }
                ]
            else:
                observations[name] = result
        all_observations = [item for values in observations.values() for item in values]
        cleanup_ok = not any(item.get("status") == "cleanup_failed" for item in all_observations)
        success = cleanup_ok and not any(
            item.get("status") in {"drift", "failed"} for item in all_observations
        )
        report: dict[str, Any] = {
            **observations,
            "cleanup_ok": cleanup_ok,
            "success": success,
        }
        rendered = json.dumps(report, sort_keys=True)
        print(rendered)
        if args.report is not None:
            args.report.write_text(rendered + "\n", encoding="utf-8")
        if not success:
            raise SystemExit(1)
        return report
    finally:
        await signed_client.close()
        await wiki_client.close()
        await disk_client.close()


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not args.acknowledge_live:
        parser.error("--acknowledge-live is required")
    if _is_service_root(args.wiki_scratch_root) or _is_service_root(args.disk_scratch_root):
        parser.error("scratch roots must not be service roots")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()

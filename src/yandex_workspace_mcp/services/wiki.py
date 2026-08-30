import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, cast
from weakref import WeakValueDictionary

import structlog

from ..auth.recovery import RecoveryTokenStore
from ..clients.base import RequestCredentials
from ..clients.signed import SignedTransferClient
from ..clients.wiki import SearchFilterUnsupported, SearchUnavailable, YandexWikiClient
from ..models.errors import ConfigurationError, ContractMismatchError, InvalidPath, PermissionDenied
from ..models.wiki import (
    AttachmentsResponse,
    AttachmentUploadResponse,
    CommentCreateInput,
    CommentsResponse,
    DescendantsInput,
    DescendantsResponse,
    GridCellsResponse,
    GridCellsUpdateInput,
    GridColumnMoveInput,
    GridColumnsAddInput,
    GridColumnsDeleteInput,
    GridCopyInput,
    GridCreateInput,
    GridDeleteInput,
    GridDeleteResponse,
    GridGetInput,
    GridMutationResponse,
    GridOperationResponse,
    GridRowMoveInput,
    GridRowsAddInput,
    GridRowsDeleteInput,
    GridsResponse,
    GridUpdateInput,
    GridUpdateResponse,
    PageAppendInput,
    PageCloneInput,
    PageCloneResponse,
    PageComment,
    PageCreateInput,
    PageDeleteInput,
    PageDeleteResponse,
    PageListInput,
    PageLocator,
    PageRecoverInput,
    PageRecoverResponse,
    PageResourceListInput,
    PageUpdateInput,
    ResourcesResponse,
    WikiAttachmentUploadInput,
    WikiGrid,
    WikiPage,
    WikiSearchInput,
    WikiSearchItem,
    WikiSearchResponse,
)
from ..policies.local_files import open_allowed_local_file
from ..policies.paths import normalize_path, validate_path, validate_wiki_slug
from ..security.audit import audit_logger

logger = structlog.get_logger()


@dataclass(frozen=True, slots=True)
class AuthorizedPage:
    page: WikiPage
    normalized_slug: str


class WikiService:
    def __init__(
        self,
        client: YandexWikiClient,
        allowed_roots: list[str],
        can_read: bool,
        can_write: bool,
        can_delete: bool,
        recovery_store: RecoveryTokenStore | None = None,
        upload_allowed_dirs: list[str] | None = None,
        max_attachment_bytes: int = 100 * 1024 * 1024,
        signed_client: SignedTransferClient | None = None,
    ):
        if (can_read or can_write or can_delete) and not allowed_roots:
            raise InvalidPath()
        self.client = client
        self.allowed_roots = list(dict.fromkeys(normalize_path(root) for root in allowed_roots))
        self.can_read = can_read
        self.can_write = can_write
        self.can_delete = can_delete
        self.recovery_store = recovery_store
        self.upload_allowed_dirs = list(upload_allowed_dirs or [])
        self.max_attachment_bytes = max_attachment_bytes
        self.signed_client = signed_client
        self._grid_locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()
        self._grid_locks_guard = asyncio.Lock()

    @asynccontextmanager
    async def _grid_mutation_lock(self, grid_id: str) -> AsyncIterator[None]:
        async with self._grid_locks_guard:
            lock = self._grid_locks.get(grid_id)
            if lock is None:
                lock = asyncio.Lock()
                self._grid_locks[grid_id] = lock
        async with lock:
            yield

    async def resolve_page(
        self,
        locator: PageLocator,
        *,
        credentials: RequestCredentials | None = None,
    ) -> AuthorizedPage:
        page = await self.client.get_page(locator, credentials=credentials)
        if not page.slug:
            raise InvalidPath()
        normalized_slug = validate_wiki_slug(page.slug, self.allowed_roots)
        return AuthorizedPage(page=page, normalized_slug=normalized_slug)

    async def resolve_grid_owner(
        self,
        grid_id: str,
        *,
        credentials: RequestCredentials | None = None,
    ) -> AuthorizedPage:
        grid = await self.client.get_grid(GridGetInput(grid_id=grid_id), credentials=credentials)
        if isinstance(grid.page.id, int):
            locator = PageLocator(page_id=grid.page.id)
        elif grid.page.slug:
            locator = PageLocator(slug=grid.page.slug)
        else:
            raise InvalidPath()
        return await self.resolve_page(locator, credentials=credentials)

    def authorize_destination(self, slug: str) -> str:
        return validate_wiki_slug(slug, self.allowed_roots)

    async def get_page(
        self,
        slug: str,
        *,
        credentials: RequestCredentials | None = None,
    ) -> WikiPage:
        if not self.can_read:
            raise PermissionDenied("Wiki read is disabled.")
        valid_slug = validate_wiki_slug(slug, self.allowed_roots)
        logger.info("wiki.get_page", slug=valid_slug)
        return (await self.resolve_page(PageLocator(slug=valid_slug), credentials=credentials)).page

    async def get_comments(
        self,
        page_input: PageListInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> CommentsResponse:
        if not self.can_read:
            raise PermissionDenied("Wiki read is disabled.")
        authorized = await self.resolve_page(page_input.locator, credentials=credentials)
        normalized = page_input.model_copy(
            update={"locator": PageLocator(page_id=authorized.page.id)}
        )
        return await self.client.get_comments(normalized, credentials=credentials)

    async def get_descendants(
        self,
        descendants_input: DescendantsInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> DescendantsResponse:
        if not self.can_read:
            raise PermissionDenied("Wiki read is disabled.")
        authorized = await self.resolve_page(descendants_input.locator, credentials=credentials)
        normalized = descendants_input.model_copy(
            update={"locator": PageLocator(page_id=authorized.page.id)}
        )
        return await self.client.get_descendants(normalized, credentials=credentials)

    async def get_resources(
        self,
        page_input: PageResourceListInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> ResourcesResponse:
        if not self.can_read:
            raise PermissionDenied("Wiki read is disabled.")
        authorized = await self.resolve_page(page_input.locator, credentials=credentials)
        normalized = page_input.model_copy(
            update={"locator": PageLocator(page_id=authorized.page.id)}
        )
        return await self.client.get_resources(normalized, credentials=credentials)

    async def get_attachments(
        self,
        page_input: PageListInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> AttachmentsResponse:
        if not self.can_read:
            raise PermissionDenied("Wiki read is disabled.")
        authorized = await self.resolve_page(page_input.locator, credentials=credentials)
        normalized = page_input.model_copy(
            update={"locator": PageLocator(page_id=authorized.page.id)}
        )
        return await self.client.get_attachments(normalized, credentials=credentials)

    async def get_grids(
        self,
        page_input: PageListInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> GridsResponse:
        if not self.can_read:
            raise PermissionDenied("Wiki read is disabled.")
        authorized = await self.resolve_page(page_input.locator, credentials=credentials)
        normalized = page_input.model_copy(
            update={"locator": PageLocator(page_id=authorized.page.id)}
        )
        return await self.client.get_grids(normalized, credentials=credentials)

    async def get_grid(
        self,
        grid_input: GridGetInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> WikiGrid:
        if not self.can_read:
            raise PermissionDenied("Wiki read is disabled.")
        await self.resolve_grid_owner(grid_input.grid_id, credentials=credentials)
        return await self.client.get_grid(grid_input, credentials=credentials)

    async def search(
        self,
        query: str,
        limit: int = 50,
        page: int = 1,
        cursor: None = None,
        *,
        credentials: RequestCredentials | None = None,
    ) -> WikiSearchResponse:
        if not self.can_read:
            raise PermissionDenied("Wiki read is disabled.")
        logger.info("wiki.search", query_length=len(query))
        search_input = WikiSearchInput(
            query=query,
            limit=limit,
            page=page,
            cursor=cursor,
        )
        semaphore = asyncio.Semaphore(4)

        async def search_root(root: str) -> WikiSearchResponse:
            cluster = None if root == "/" else root.removeprefix("/")
            async with semaphore:
                return await self.client.search(
                    search_input,
                    cluster=cluster,
                    credentials=credentials,
                )

        try:
            if "/" in self.allowed_roots:
                responses = [await search_root("/")]
                globally_filtered = False
            else:
                responses = await asyncio.gather(
                    *(search_root(root) for root in self.allowed_roots[:20])
                )
                globally_filtered = False
        except SearchFilterUnsupported:
            responses = [
                await self.client.search(
                    search_input,
                    cluster=None,
                    credentials=credentials,
                )
            ]
            globally_filtered = True
        except (SearchUnavailable, ContractMismatchError):
            return await self._descendants_fallback(
                query=query,
                limit=limit,
                credentials=credentials,
            )

        merged = self._merge_authorized_results(responses, limit=limit)
        upstream_count = sum(len(response.results) for response in responses)
        return WikiSearchResponse(
            results=merged,
            truncated_by_upstream=(
                globally_filtered and len(merged) < limit and upstream_count >= limit
            ),
            pagination_exhausted=any(response.pagination_exhausted for response in responses),
        )

    def _merge_authorized_results(
        self, responses: list[WikiSearchResponse], *, limit: int
    ) -> list[WikiSearchItem]:
        merged: list[WikiSearchItem] = []
        seen: set[tuple[str, int | str, str]] = set()
        for response in responses:
            for item in response.results:
                if not item.slug:
                    continue
                try:
                    validate_path("/" + item.slug.strip("/"), self.allowed_roots)
                except InvalidPath:
                    continue
                identity: tuple[str, int | str, str] = (
                    item.type,
                    item.id if item.id is not None else item.slug,
                    item.url or "",
                )
                if identity in seen:
                    continue
                seen.add(identity)
                merged.append(item)
                if len(merged) >= limit:
                    return merged
        return merged

    async def _descendants_fallback(
        self,
        *,
        query: str,
        limit: int,
        credentials: RequestCredentials | None,
    ) -> WikiSearchResponse:
        query_normalized = query.casefold()
        results: list[WikiSearchItem] = []
        seen_ids: set[tuple[int, str | None]] = set()
        for root in self.allowed_roots[:20]:
            cursor: str | None = None
            seen_cursors: set[str] = set()
            for _page_number in range(20):
                batch = await self.client.get_descendants(
                    DescendantsInput(
                        locator=PageLocator(slug=root.removeprefix("/") or "/"),
                        page_size=100,
                        cursor=cursor,
                    ),
                    credentials=credentials,
                )
                for item in batch.results:
                    identity = (item.id, item.slug)
                    if identity in seen_ids or not item.slug:
                        continue
                    seen_ids.add(identity)
                    try:
                        validate_path("/" + item.slug.strip("/"), self.allowed_roots)
                    except InvalidPath:
                        continue
                    if query_normalized in item.slug.casefold():
                        results.append(
                            WikiSearchItem(
                                id=item.id,
                                slug=item.slug,
                                title=None,
                                content_excerpt=None,
                                type="page",
                            )
                        )
                        if len(results) >= limit:
                            return WikiSearchResponse(
                                results=results,
                                degraded=True,
                                search_mode="descendants",
                            )
                cursor = batch.next_cursor
                if not cursor or cursor in seen_cursors:
                    break
                seen_cursors.add(cursor)
        return WikiSearchResponse(
            results=results,
            degraded=True,
            search_mode="descendants",
        )

    async def get_tree(self, slug: str) -> dict[str, Any]:
        if not self.can_read:
            raise PermissionDenied("Wiki read is disabled.")
        valid_slug = validate_wiki_slug(slug, self.allowed_roots)
        logger.info("wiki.get_tree", slug=valid_slug)
        result = await self.get_descendants(DescendantsInput(locator=PageLocator(slug=valid_slug)))
        return result.model_dump(mode="json")

    async def create_page(
        self,
        page_input: PageCreateInput | str,
        title: str | None = None,
        body: str | None = None,
        *,
        credentials: RequestCredentials | None = None,
    ) -> WikiPage:
        if not self.can_write:
            raise PermissionDenied("Wiki write is disabled.")
        if isinstance(page_input, str):
            if title is None or body is None:
                raise ValueError("title and body are required")
            page_input = PageCreateInput(slug=page_input, title=title, content=body)
        valid_slug = self.authorize_destination(page_input.slug)
        logger.info("wiki.create_page", slug=valid_slug)
        result = await self.client.create_page(
            page_input.model_copy(update={"slug": valid_slug}), credentials=credentials
        )
        audit_logger.log("wiki.create_page", slug=valid_slug, result="success")
        return result

    async def update_page(
        self,
        page_input: PageUpdateInput | str,
        body: str | None = None,
        title: str | None = None,
        *,
        credentials: RequestCredentials | None = None,
    ) -> WikiPage:
        if not self.can_write:
            raise PermissionDenied("Wiki write is disabled.")
        if isinstance(page_input, str):
            if body is None:
                raise ValueError("body is required")
            page_input = PageUpdateInput(
                locator=PageLocator(slug=page_input),
                title=title,
                content=body,
            )
        authorized = await self.resolve_page(page_input.locator, credentials=credentials)
        logger.info("wiki.update_page", slug=authorized.normalized_slug)
        result = await self.client.update_page(
            authorized.page.id,
            page_input.model_copy(update={"locator": PageLocator(page_id=authorized.page.id)}),
            credentials=credentials,
        )
        audit_logger.log("wiki.update_page", slug=authorized.normalized_slug, result="success")
        return result

    async def append_page(
        self,
        page_input: PageAppendInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> WikiPage:
        if not self.can_write:
            raise PermissionDenied("Wiki write is disabled.")
        authorized = await self.resolve_page(page_input.locator, credentials=credentials)
        result = await self.client.append_page(
            authorized.page.id,
            page_input.model_copy(update={"locator": PageLocator(page_id=authorized.page.id)}),
            credentials=credentials,
        )
        audit_logger.log("wiki.append_page", slug=authorized.normalized_slug, result="success")
        return result

    async def clone_page(
        self,
        page_input: PageCloneInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> PageCloneResponse:
        if not self.can_write:
            raise PermissionDenied("Wiki write is disabled.")
        source = await self.resolve_page(page_input.source, credentials=credentials)
        try:
            destination = self.authorize_destination(page_input.destination_slug)
        except InvalidPath as exc:
            raise PermissionDenied() from exc
        result = await self.client.clone_page(
            source.page.id,
            page_input.model_copy(
                update={
                    "source": PageLocator(page_id=source.page.id),
                    "destination_slug": destination,
                }
            ),
            credentials=credentials,
        )
        audit_logger.log("wiki.clone_page", slug=destination, result="success")
        return result

    async def add_comment(
        self,
        comment_input: CommentCreateInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> PageComment:
        if not self.can_write:
            raise PermissionDenied("Wiki write is disabled.")
        authorized = await self.resolve_page(comment_input.locator, credentials=credentials)
        result = await self.client.add_comment(
            authorized.page.id,
            comment_input.model_copy(update={"locator": PageLocator(page_id=authorized.page.id)}),
            credentials=credentials,
        )
        audit_logger.log("wiki.add_comment", slug=authorized.normalized_slug, result="success")
        return result

    async def delete_page(
        self,
        page_input: PageDeleteInput,
        *,
        principal_id: str,
        credentials: RequestCredentials | None = None,
    ) -> PageDeleteResponse:
        if not self.can_delete:
            raise PermissionDenied("Wiki delete is disabled.")
        if self.recovery_store is None:
            raise ConfigurationError("Wiki recovery token store is unavailable.")
        authorized = await self.resolve_page(page_input.locator, credentials=credentials)
        upstream_token = await self.client.delete_page(
            authorized.page.id,
            credentials=credentials,
        )
        handle = await self.recovery_store.put(
            upstream_token=upstream_token,
            principal_id=principal_id,
            normalized_locator=authorized.normalized_slug,
        )
        audit_logger.log("wiki.delete_page", slug=authorized.normalized_slug, result="success")
        return PageDeleteResponse(recovery_token=handle)

    async def recover_page(
        self,
        page_input: PageRecoverInput,
        *,
        principal_id: str,
        credentials: RequestCredentials | None = None,
    ) -> PageRecoverResponse:
        if not self.can_delete:
            raise PermissionDenied("Wiki recovery is disabled.")
        if self.recovery_store is None:
            raise ConfigurationError("Wiki recovery token store is unavailable.")
        record = await self.recovery_store.consume(
            page_input.recovery_token,
            principal_id=principal_id,
        )
        self.authorize_destination(record.normalized_locator)
        result = await self.client.recover_page(
            record.upstream_token,
            credentials=credentials,
        )
        audit_logger.log("wiki.recover_page", slug=record.normalized_locator, result="success")
        return result

    async def upload_attachment(
        self,
        upload_input: WikiAttachmentUploadInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> AttachmentUploadResponse:
        if not self.can_write or not self.upload_allowed_dirs:
            raise PermissionDenied("Wiki local attachment upload is disabled.")
        authorized = await self.resolve_page(upload_input.locator, credentials=credentials)
        opened = open_allowed_local_file(
            upload_input.file_path,
            self.upload_allowed_dirs,
            max_bytes=self.max_attachment_bytes,
        )
        try:
            result = await self.client.upload_attachment(
                authorized.page.id,
                opened,
                upload_input.model_copy(
                    update={"locator": PageLocator(page_id=authorized.page.id)}
                ),
                signed_client=self.signed_client,
                credentials=credentials,
            )
        finally:
            opened.close()
        audit_logger.log(
            "wiki.upload_attachment", slug=authorized.normalized_slug, result="success"
        )
        return result

    async def create_grid(
        self,
        grid_input: GridCreateInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> WikiGrid:
        if not self.can_write:
            raise PermissionDenied("Wiki write is disabled.")
        owner = await self.resolve_page(grid_input.locator, credentials=credentials)
        result = await self.client.create_grid(
            owner.page.id,
            grid_input.model_copy(update={"locator": PageLocator(page_id=owner.page.id)}),
            credentials=credentials,
        )
        audit_logger.log("wiki.create_grid", slug=owner.normalized_slug, result="success")
        return result

    async def update_grid(
        self,
        grid_input: GridUpdateInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> GridUpdateResponse:
        if not self.can_write:
            raise PermissionDenied("Wiki write is disabled.")
        async with self._grid_mutation_lock(grid_input.grid_id):
            owner = await self.resolve_grid_owner(grid_input.grid_id, credentials=credentials)
            result = await self.client.update_grid(grid_input, credentials=credentials)
        audit_logger.log("wiki.update_grid", slug=owner.normalized_slug, result="success")
        return result

    async def copy_grid(
        self,
        grid_input: GridCopyInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> GridOperationResponse:
        if not self.can_write:
            raise PermissionDenied("Wiki write is disabled.")
        async with self._grid_mutation_lock(grid_input.grid_id):
            source = await self.resolve_grid_owner(grid_input.grid_id, credentials=credentials)
            destination = await self.resolve_page(grid_input.destination, credentials=credentials)
            result = await self.client.copy_grid(
                grid_input.grid_id,
                destination_slug=destination.normalized_slug,
                title=grid_input.title,
                credentials=credentials,
            )
        audit_logger.log(
            "wiki.copy_grid",
            slug=source.normalized_slug,
            destination_slug=destination.normalized_slug,
            result="success",
        )
        return result

    async def delete_grid(
        self,
        grid_input: GridDeleteInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> GridDeleteResponse:
        if not self.can_delete:
            raise PermissionDenied("Wiki delete is disabled.")
        async with self._grid_mutation_lock(grid_input.grid_id):
            owner = await self.resolve_grid_owner(grid_input.grid_id, credentials=credentials)
            result = await self.client.delete_grid(grid_input, credentials=credentials)
        audit_logger.log("wiki.delete_grid", slug=owner.normalized_slug, result="success")
        return result

    async def add_grid_rows(
        self,
        grid_input: GridRowsAddInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> GridMutationResponse:
        return cast(
            GridMutationResponse,
            await self._run_grid_write("add_grid_rows", grid_input, credentials=credentials),
        )

    async def update_grid_cells(
        self,
        grid_input: GridCellsUpdateInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> GridCellsResponse:
        return cast(
            GridCellsResponse,
            await self._run_grid_write("update_grid_cells", grid_input, credentials=credentials),
        )

    async def delete_grid_rows(
        self,
        grid_input: GridRowsDeleteInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> GridMutationResponse:
        if not self.can_delete:
            raise PermissionDenied("Wiki delete is disabled.")
        return cast(
            GridMutationResponse,
            await self._run_grid_write(
                "delete_grid_rows",
                grid_input,
                credentials=credentials,
                require_write=False,
            ),
        )

    async def move_grid_row(
        self,
        grid_input: GridRowMoveInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> GridMutationResponse:
        return cast(
            GridMutationResponse,
            await self._run_grid_write("move_grid_row", grid_input, credentials=credentials),
        )

    async def add_grid_columns(
        self,
        grid_input: GridColumnsAddInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> GridMutationResponse:
        return cast(
            GridMutationResponse,
            await self._run_grid_write("add_grid_columns", grid_input, credentials=credentials),
        )

    async def delete_grid_columns(
        self,
        grid_input: GridColumnsDeleteInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> GridMutationResponse:
        if not self.can_delete:
            raise PermissionDenied("Wiki delete is disabled.")
        return cast(
            GridMutationResponse,
            await self._run_grid_write(
                "delete_grid_columns",
                grid_input,
                credentials=credentials,
                require_write=False,
            ),
        )

    async def move_grid_column(
        self,
        grid_input: GridColumnMoveInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> GridMutationResponse:
        return cast(
            GridMutationResponse,
            await self._run_grid_write("move_grid_column", grid_input, credentials=credentials),
        )

    async def _run_grid_write(
        self,
        method_name: str,
        grid_input: (
            GridRowsAddInput
            | GridCellsUpdateInput
            | GridRowsDeleteInput
            | GridRowMoveInput
            | GridColumnsAddInput
            | GridColumnsDeleteInput
            | GridColumnMoveInput
        ),
        *,
        credentials: RequestCredentials | None,
        require_write: bool = True,
    ) -> GridMutationResponse | GridCellsResponse:
        if require_write and not self.can_write:
            raise PermissionDenied("Wiki write is disabled.")
        async with self._grid_mutation_lock(grid_input.grid_id):
            owner = await self.resolve_grid_owner(grid_input.grid_id, credentials=credentials)
            method = getattr(self.client, method_name)
            result = await method(grid_input, credentials=credentials)
        audit_logger.log(f"wiki.{method_name}", slug=owner.normalized_slug, result="success")
        return result

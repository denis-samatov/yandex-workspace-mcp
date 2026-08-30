from typing import Annotated, Any, Literal, Protocol

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from ..auth.scopes import OperationClass, WorkspacePrincipal, WorkspaceScope, require_scope
from ..config import Settings
from ..models.wiki import (
    AttachmentsResponse,
    AttachmentUploadResponse,
    CommentCreateInput,
    CommentsResponse,
    Cursor,
    DescendantsInput,
    DescendantsResponse,
    GridCellsResponse,
    GridCellsUpdateInput,
    GridCellUpdate,
    GridColumnCreate,
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
    GridSort,
    GridsResponse,
    GridUpdateInput,
    GridUpdateResponse,
    JsonScalar,
    OpaqueID,
    PageAppendInput,
    PageCloneInput,
    PageCloneResponse,
    PageComment,
    PageDeleteInput,
    PageDeleteResponse,
    PageListInput,
    PageLocator,
    PageRecoverInput,
    PageRecoverResponse,
    PageResourceListInput,
    ResourcesResponse,
    WikiAttachmentUploadInput,
    WikiGrid,
    WikiPage,
    WikiSearchResponse,
)
from ..services.wiki import WikiService


class WikiApplication(Protocol):
    @property
    def principal(self) -> WorkspacePrincipal: ...

    def require_wiki_service(self) -> WikiService: ...


READ_ANNOTATIONS = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)
WRITE_ANNOTATIONS = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=False,
)
DESTRUCTIVE_ANNOTATIONS = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=True,
    idempotent_hint=False,
    open_world_hint=False,
)


def _scope_meta(scope: WorkspaceScope) -> dict[str, list[str]]:
    return {"required_scopes": [scope.value]}


def register_wiki_tools(mcp: MCPServer, application: WikiApplication, settings: Settings) -> None:
    if not settings.yandex_wiki_enabled:
        return
    if settings.wiki_read:

        @mcp.tool(
            name="wiki_search",
            description="Search Yandex Wiki pages",
            annotations=READ_ANNOTATIONS,
            meta=_scope_meta(WorkspaceScope.READ),
        )
        async def wiki_search(
            query: str,
            limit: Annotated[int, Field(ge=1, le=50)] = 50,
            page: Annotated[int, Field(ge=1)] = 1,
            cursor: None = None,
        ) -> WikiSearchResponse:
            require_scope(application.principal, OperationClass.READ)
            return await application.require_wiki_service().search(query, limit, page, cursor)

        @mcp.tool(
            name="wiki_get_page",
            description="Get a Yandex Wiki page by slug",
            annotations=READ_ANNOTATIONS,
            meta=_scope_meta(WorkspaceScope.READ),
        )
        async def wiki_get_page(slug: str) -> WikiPage:
            require_scope(application.principal, OperationClass.READ)
            return await application.require_wiki_service().get_page(slug)

        @mcp.tool(
            name="wiki_get_tree",
            description="Get the tree of pages under a Wiki slug",
            annotations=READ_ANNOTATIONS,
            meta=_scope_meta(WorkspaceScope.READ),
        )
        async def wiki_get_tree(slug: str) -> dict[str, Any]:
            require_scope(application.principal, OperationClass.READ)
            return await application.require_wiki_service().get_tree(slug)

        @mcp.tool(
            name="wiki_get_descendants",
            description="List descendants of a Wiki page",
            annotations=READ_ANNOTATIONS,
            meta=_scope_meta(WorkspaceScope.READ),
        )
        async def wiki_get_descendants(
            locator: PageLocator,
            include_self: bool = False,
            page_size: Annotated[int, Field(ge=1, le=100)] = 100,
            cursor: Cursor | None = None,
        ) -> DescendantsResponse:
            require_scope(application.principal, OperationClass.READ)
            return await application.require_wiki_service().get_descendants(
                DescendantsInput(
                    locator=locator,
                    include_self=include_self,
                    page_size=page_size,
                    cursor=cursor,
                )
            )

        @mcp.tool(
            name="wiki_get_comments",
            description="List comments on a Wiki page",
            annotations=READ_ANNOTATIONS,
            meta=_scope_meta(WorkspaceScope.READ),
        )
        async def wiki_get_comments(
            locator: PageLocator,
            page_size: Annotated[int, Field(ge=1, le=100)] = 100,
            cursor: Cursor | None = None,
        ) -> CommentsResponse:
            require_scope(application.principal, OperationClass.READ)
            return await application.require_wiki_service().get_comments(
                PageListInput(locator=locator, page_size=page_size, cursor=cursor)
            )

        @mcp.tool(
            name="wiki_get_resources",
            description="List resources attached to a Wiki page",
            annotations=READ_ANNOTATIONS,
            meta=_scope_meta(WorkspaceScope.READ),
        )
        async def wiki_get_resources(
            locator: PageLocator,
            resource_types: Annotated[
                list[Literal["attachment", "grid"]], Field(min_length=1, max_length=2)
            ]
            | None = None,
            page_size: Annotated[int, Field(ge=1, le=100)] = 100,
            cursor: Cursor | None = None,
        ) -> ResourcesResponse:
            require_scope(application.principal, OperationClass.READ)
            return await application.require_wiki_service().get_resources(
                PageResourceListInput(
                    locator=locator,
                    resource_types=resource_types,
                    page_size=page_size,
                    cursor=cursor,
                )
            )

        @mcp.tool(
            name="wiki_get_attachments",
            description="List files attached to a Wiki page",
            annotations=READ_ANNOTATIONS,
            meta=_scope_meta(WorkspaceScope.READ),
        )
        async def wiki_get_attachments(
            locator: PageLocator,
            page_size: Annotated[int, Field(ge=1, le=100)] = 100,
            cursor: Cursor | None = None,
        ) -> AttachmentsResponse:
            require_scope(application.principal, OperationClass.READ)
            return await application.require_wiki_service().get_attachments(
                PageListInput(locator=locator, page_size=page_size, cursor=cursor)
            )

        @mcp.tool(
            name="wiki_get_grids",
            description="List dynamic tables attached to a Wiki page",
            annotations=READ_ANNOTATIONS,
            meta=_scope_meta(WorkspaceScope.READ),
        )
        async def wiki_get_grids(
            locator: PageLocator,
            page_size: Annotated[int, Field(ge=1, le=100)] = 100,
            cursor: Cursor | None = None,
        ) -> GridsResponse:
            require_scope(application.principal, OperationClass.READ)
            return await application.require_wiki_service().get_grids(
                PageListInput(locator=locator, page_size=page_size, cursor=cursor)
            )

        @mcp.tool(
            name="wiki_get_grid",
            description="Get a Wiki dynamic table",
            annotations=READ_ANNOTATIONS,
            meta=_scope_meta(WorkspaceScope.READ),
        )
        async def wiki_get_grid(
            grid_id: OpaqueID,
            revision: Annotated[int, Field(ge=0)] | None = None,
            row_ids: Annotated[list[OpaqueID], Field(min_length=1, max_length=100)] | None = None,
            column_slugs: Annotated[list[OpaqueID], Field(min_length=1, max_length=100)]
            | None = None,
        ) -> WikiGrid:
            require_scope(application.principal, OperationClass.READ)
            return await application.require_wiki_service().get_grid(
                GridGetInput(
                    grid_id=grid_id,
                    revision=revision,
                    row_ids=row_ids,
                    column_slugs=column_slugs,
                )
            )

    if settings.wiki_write:

        @mcp.tool(
            name="wiki_create_page",
            description="Create a new Yandex Wiki page",
            annotations=WRITE_ANNOTATIONS,
            meta=_scope_meta(WorkspaceScope.WRITE),
        )
        async def wiki_create_page(slug: str, title: str, body: str) -> WikiPage:
            require_scope(application.principal, OperationClass.WRITE)
            return await application.require_wiki_service().create_page(slug, title, body)

        @mcp.tool(
            name="wiki_update_page",
            description="Update a Yandex Wiki page",
            annotations=WRITE_ANNOTATIONS,
            meta=_scope_meta(WorkspaceScope.WRITE),
        )
        async def wiki_update_page(slug: str, body: str, title: str | None = None) -> WikiPage:
            require_scope(application.principal, OperationClass.WRITE)
            return await application.require_wiki_service().update_page(slug, body, title=title)

        @mcp.tool(
            name="wiki_append_page",
            description="Append content to a Wiki page",
            annotations=WRITE_ANNOTATIONS,
            meta=_scope_meta(WorkspaceScope.WRITE),
        )
        async def wiki_append_page(
            locator: PageLocator,
            content: Annotated[str, Field(min_length=1, max_length=2_000_000)],
            location: Literal["top", "bottom"] = "bottom",
            anchor: OpaqueID | None = None,
        ) -> WikiPage:
            require_scope(application.principal, OperationClass.WRITE)
            return await application.require_wiki_service().append_page(
                PageAppendInput(
                    locator=locator,
                    content=content,
                    location=location,
                    anchor=anchor,
                )
            )

        @mcp.tool(
            name="wiki_clone_page",
            description="Clone a Wiki page",
            annotations=WRITE_ANNOTATIONS,
            meta=_scope_meta(WorkspaceScope.WRITE),
        )
        async def wiki_clone_page(
            source: PageLocator,
            destination_slug: Annotated[str, Field(min_length=1, max_length=1024)],
            title: Annotated[str, Field(min_length=1, max_length=500)] | None = None,
        ) -> PageCloneResponse:
            require_scope(application.principal, OperationClass.WRITE)
            return await application.require_wiki_service().clone_page(
                PageCloneInput(
                    source=source,
                    destination_slug=destination_slug,
                    title=title,
                )
            )

        @mcp.tool(
            name="wiki_add_comment",
            description="Add a comment to a Wiki page",
            annotations=WRITE_ANNOTATIONS,
            meta=_scope_meta(WorkspaceScope.WRITE),
        )
        async def wiki_add_comment(
            locator: PageLocator,
            body: Annotated[str, Field(min_length=1, max_length=100_000)],
            parent_comment_id: OpaqueID | None = None,
        ) -> PageComment:
            require_scope(application.principal, OperationClass.WRITE)
            return await application.require_wiki_service().add_comment(
                CommentCreateInput(
                    locator=locator,
                    body=body,
                    parent_comment_id=parent_comment_id,
                )
            )

        @mcp.tool(
            name="wiki_create_grid",
            description="Create a Wiki dynamic table",
            annotations=WRITE_ANNOTATIONS,
            meta=_scope_meta(WorkspaceScope.WRITE),
        )
        async def wiki_create_grid(
            locator: PageLocator,
            title: Annotated[str, Field(min_length=1, max_length=255)],
        ) -> WikiGrid:
            require_scope(application.principal, OperationClass.WRITE)
            return await application.require_wiki_service().create_grid(
                GridCreateInput(locator=locator, title=title)
            )

        @mcp.tool(
            name="wiki_update_grid",
            description="Update a Wiki dynamic table",
            annotations=WRITE_ANNOTATIONS,
            meta=_scope_meta(WorkspaceScope.WRITE),
        )
        async def wiki_update_grid(
            grid_id: OpaqueID,
            revision: Annotated[int, Field(ge=0)],
            title: Annotated[str, Field(min_length=1, max_length=255)] | None = None,
            default_sort: Annotated[list[GridSort], Field(min_length=1, max_length=16)]
            | None = None,
        ) -> GridUpdateResponse:
            require_scope(application.principal, OperationClass.WRITE)
            return await application.require_wiki_service().update_grid(
                GridUpdateInput(
                    grid_id=grid_id,
                    revision=revision,
                    title=title,
                    default_sort=default_sort,
                )
            )

        @mcp.tool(
            name="wiki_copy_grid",
            description="Copy a Wiki dynamic table",
            annotations=WRITE_ANNOTATIONS,
            meta=_scope_meta(WorkspaceScope.WRITE),
        )
        async def wiki_copy_grid(
            grid_id: OpaqueID,
            destination: PageLocator,
            title: Annotated[str, Field(min_length=1, max_length=255)] | None = None,
        ) -> GridOperationResponse:
            require_scope(application.principal, OperationClass.WRITE)
            return await application.require_wiki_service().copy_grid(
                GridCopyInput(grid_id=grid_id, destination=destination, title=title)
            )

        @mcp.tool(
            name="wiki_add_grid_rows",
            description="Add rows to a Wiki dynamic table",
            annotations=WRITE_ANNOTATIONS,
            meta=_scope_meta(WorkspaceScope.WRITE),
        )
        async def wiki_add_grid_rows(
            grid_id: OpaqueID,
            revision: Annotated[int, Field(ge=0)],
            rows: Annotated[list[dict[OpaqueID, JsonScalar]], Field(min_length=1, max_length=1000)],
            position: Annotated[int, Field(ge=0)] | None = None,
            after_row_id: OpaqueID | None = None,
        ) -> GridMutationResponse:
            require_scope(application.principal, OperationClass.WRITE)
            return await application.require_wiki_service().add_grid_rows(
                GridRowsAddInput(
                    grid_id=grid_id,
                    revision=revision,
                    rows=rows,
                    position=position,
                    after_row_id=after_row_id,
                )
            )

        @mcp.tool(
            name="wiki_update_grid_cells",
            description="Update cells in a Wiki dynamic table",
            annotations=WRITE_ANNOTATIONS,
            meta=_scope_meta(WorkspaceScope.WRITE),
        )
        async def wiki_update_grid_cells(
            grid_id: OpaqueID,
            revision: Annotated[int, Field(ge=0)],
            cells: Annotated[list[GridCellUpdate], Field(min_length=1, max_length=1000)],
        ) -> GridCellsResponse:
            require_scope(application.principal, OperationClass.WRITE)
            return await application.require_wiki_service().update_grid_cells(
                GridCellsUpdateInput(grid_id=grid_id, revision=revision, cells=cells)
            )

        @mcp.tool(
            name="wiki_move_grid_row",
            description="Move a row in a Wiki dynamic table",
            annotations=WRITE_ANNOTATIONS,
            meta=_scope_meta(WorkspaceScope.WRITE),
        )
        async def wiki_move_grid_row(
            grid_id: OpaqueID,
            revision: Annotated[int, Field(ge=0)],
            row_id: OpaqueID,
            position: Annotated[int, Field(ge=0)] | None = None,
            after_row_id: OpaqueID | None = None,
        ) -> GridMutationResponse:
            require_scope(application.principal, OperationClass.WRITE)
            return await application.require_wiki_service().move_grid_row(
                GridRowMoveInput(
                    grid_id=grid_id,
                    revision=revision,
                    row_id=row_id,
                    position=position,
                    after_row_id=after_row_id,
                )
            )

        @mcp.tool(
            name="wiki_add_grid_columns",
            description="Add columns to a Wiki dynamic table",
            annotations=WRITE_ANNOTATIONS,
            meta=_scope_meta(WorkspaceScope.WRITE),
        )
        async def wiki_add_grid_columns(
            grid_id: OpaqueID,
            revision: Annotated[int, Field(ge=0)],
            columns: Annotated[list[GridColumnCreate], Field(min_length=1, max_length=100)],
            position: Annotated[int, Field(ge=0)] | None = None,
        ) -> GridMutationResponse:
            require_scope(application.principal, OperationClass.WRITE)
            return await application.require_wiki_service().add_grid_columns(
                GridColumnsAddInput(
                    grid_id=grid_id,
                    revision=revision,
                    columns=columns,
                    position=position,
                )
            )

        @mcp.tool(
            name="wiki_move_grid_column",
            description="Move a column in a Wiki dynamic table",
            annotations=WRITE_ANNOTATIONS,
            meta=_scope_meta(WorkspaceScope.WRITE),
        )
        async def wiki_move_grid_column(
            grid_id: OpaqueID,
            revision: Annotated[int, Field(ge=0)],
            column_slug: OpaqueID,
            position: Annotated[int, Field(ge=0)],
        ) -> GridMutationResponse:
            require_scope(application.principal, OperationClass.WRITE)
            return await application.require_wiki_service().move_grid_column(
                GridColumnMoveInput(
                    grid_id=grid_id,
                    revision=revision,
                    column_slug=column_slug,
                    position=position,
                )
            )

        if settings.mcp_transport == "stdio" and settings.wiki_upload_allowed_dirs:

            @mcp.tool(
                name="wiki_upload_attachment",
                description="Attach an allowlisted local file to a Wiki page",
                annotations=WRITE_ANNOTATIONS,
                meta=_scope_meta(WorkspaceScope.WRITE),
            )
            async def wiki_upload_attachment(
                locator: PageLocator,
                file_path: Annotated[str, Field(min_length=1, max_length=4096)],
                append_markup: bool = False,
                append_location: Literal["top", "bottom"] = "bottom",
            ) -> AttachmentUploadResponse:
                require_scope(application.principal, OperationClass.WRITE)
                return await application.require_wiki_service().upload_attachment(
                    WikiAttachmentUploadInput(
                        locator=locator,
                        file_path=file_path,
                        append_markup=append_markup,
                        append_location=append_location,
                    )
                )

    if settings.wiki_delete:

        @mcp.tool(
            name="wiki_delete_page",
            description="Delete a Wiki page and return an opaque recovery handle",
            annotations=DESTRUCTIVE_ANNOTATIONS,
            meta=_scope_meta(WorkspaceScope.DELETE),
        )
        async def wiki_delete_page(locator: PageLocator) -> PageDeleteResponse:
            require_scope(application.principal, OperationClass.DELETE)
            return await application.require_wiki_service().delete_page(
                PageDeleteInput(locator=locator),
                principal_id=application.principal.principal_id,
            )

        @mcp.tool(
            name="wiki_recover_page",
            description="Recover a Wiki page using an opaque recovery handle",
            annotations=WRITE_ANNOTATIONS,
            meta=_scope_meta(WorkspaceScope.DELETE),
        )
        async def wiki_recover_page(recovery_token: OpaqueID) -> PageRecoverResponse:
            require_scope(application.principal, OperationClass.DELETE)
            return await application.require_wiki_service().recover_page(
                PageRecoverInput(recovery_token=recovery_token),
                principal_id=application.principal.principal_id,
            )

        @mcp.tool(
            name="wiki_delete_grid",
            description="Delete a Wiki dynamic table",
            annotations=DESTRUCTIVE_ANNOTATIONS,
            meta=_scope_meta(WorkspaceScope.DELETE),
        )
        async def wiki_delete_grid(
            grid_id: OpaqueID,
            revision: Annotated[int, Field(ge=0)] | None = None,
        ) -> GridDeleteResponse:
            require_scope(application.principal, OperationClass.DELETE)
            return await application.require_wiki_service().delete_grid(
                GridDeleteInput(grid_id=grid_id, revision=revision)
            )

        @mcp.tool(
            name="wiki_delete_grid_rows",
            description="Delete rows from a Wiki dynamic table",
            annotations=DESTRUCTIVE_ANNOTATIONS,
            meta=_scope_meta(WorkspaceScope.DELETE),
        )
        async def wiki_delete_grid_rows(
            grid_id: OpaqueID,
            revision: Annotated[int, Field(ge=0)],
            row_ids: Annotated[list[OpaqueID], Field(min_length=1, max_length=1000)],
        ) -> GridMutationResponse:
            require_scope(application.principal, OperationClass.DELETE)
            return await application.require_wiki_service().delete_grid_rows(
                GridRowsDeleteInput(grid_id=grid_id, revision=revision, row_ids=row_ids)
            )

        @mcp.tool(
            name="wiki_delete_grid_columns",
            description="Delete columns from a Wiki dynamic table",
            annotations=DESTRUCTIVE_ANNOTATIONS,
            meta=_scope_meta(WorkspaceScope.DELETE),
        )
        async def wiki_delete_grid_columns(
            grid_id: OpaqueID,
            revision: Annotated[int, Field(ge=0)],
            column_slugs: Annotated[list[OpaqueID], Field(min_length=1, max_length=100)],
        ) -> GridMutationResponse:
            require_scope(application.principal, OperationClass.DELETE)
            return await application.require_wiki_service().delete_grid_columns(
                GridColumnsDeleteInput(
                    grid_id=grid_id,
                    revision=revision,
                    column_slugs=column_slugs,
                )
            )

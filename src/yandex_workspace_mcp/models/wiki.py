import math
from collections.abc import Hashable, Sequence
from typing import Annotated, Literal, TypeGuard

from pydantic import AliasChoices, Field, model_validator

from .base import PublicModel, WireModel

WIKI_MAX_CONTENT_CHARS = 2_000_000
WIKI_MAX_COMMENT_CHARS = 100_000

Query = Annotated[str, Field(min_length=1, max_length=1000)]
Slug = Annotated[str, Field(min_length=1, max_length=1024)]
Cursor = Annotated[str, Field(min_length=1, max_length=4096)]
OpaqueID = Annotated[str, Field(min_length=1, max_length=2048)]
JsonFloat = Annotated[float, Field(allow_inf_nan=False)]
type JsonScalar = str | bool | int | JsonFloat | None


def _duplicates(values: Sequence[Hashable]) -> bool:
    return len(values) != len(set(values))


class WikiSearchInput(PublicModel):
    query: Query
    limit: Annotated[int, Field(ge=1, le=50)] = 50
    page: Annotated[int, Field(ge=1)] = 1
    cursor: None = None


class PageLocator(PublicModel):
    page_id: Annotated[int, Field(gt=0)] | None = None
    slug: Slug | None = None
    url: Annotated[str, Field(min_length=1, max_length=2048)] | None = None

    @model_validator(mode="after")
    def validate_exactly_one_locator(self) -> "PageLocator":
        if sum(value is not None for value in (self.page_id, self.slug, self.url)) != 1:
            raise ValueError("provide exactly one page locator")
        return self


class PageLocatorInput(PublicModel):
    locator: PageLocator


class PageDeleteInput(PageLocatorInput):
    pass


class DescendantsInput(PageLocatorInput):
    include_self: bool = False
    page_size: Annotated[int, Field(ge=1, le=100)] = 100
    cursor: Cursor | None = None


class PageListInput(PageLocatorInput):
    page_size: Annotated[int, Field(ge=1, le=100)] = 100
    cursor: Cursor | None = None


class PageResourceListInput(PageListInput):
    resource_types: (
        Annotated[list[Literal["attachment", "grid"]], Field(min_length=1, max_length=2)] | None
    ) = None

    @model_validator(mode="after")
    def validate_unique_resource_types(self) -> "PageResourceListInput":
        if self.resource_types and _duplicates(self.resource_types):
            raise ValueError("resource types must be unique")
        return self


class GridGetInput(PublicModel):
    grid_id: OpaqueID
    revision: Annotated[int, Field(ge=0)] | None = None
    row_ids: Annotated[list[OpaqueID], Field(min_length=1, max_length=100)] | None = None
    column_slugs: Annotated[list[OpaqueID], Field(min_length=1, max_length=100)] | None = None

    @model_validator(mode="after")
    def validate_unique_filters(self) -> "GridGetInput":
        if self.row_ids and _duplicates(self.row_ids):
            raise ValueError("row IDs must be unique")
        if self.column_slugs and _duplicates(self.column_slugs):
            raise ValueError("column slugs must be unique")
        return self


class PageCreateInput(PublicModel):
    slug: Slug
    title: Annotated[str, Field(min_length=1, max_length=500)]
    content: Annotated[str, Field(max_length=WIKI_MAX_CONTENT_CHARS)]


class PageUpdateInput(PageLocatorInput):
    title: Annotated[str, Field(min_length=1, max_length=500)] | None = None
    content: Annotated[str, Field(max_length=WIKI_MAX_CONTENT_CHARS)] | None = None
    allow_merge: bool = False
    is_silent: bool = False

    @model_validator(mode="after")
    def validate_mutable_field(self) -> "PageUpdateInput":
        if self.title is None and self.content is None:
            raise ValueError("title or content is required")
        return self


class PageAppendInput(PageLocatorInput):
    content: Annotated[str, Field(min_length=1, max_length=WIKI_MAX_CONTENT_CHARS)]
    location: Literal["top", "bottom"] = "bottom"
    anchor: Annotated[str, Field(min_length=1, max_length=1024)] | None = None

    @model_validator(mode="after")
    def validate_anchor_location(self) -> "PageAppendInput":
        if self.anchor is not None and self.location != "bottom":
            raise ValueError("anchor and non-default location are mutually exclusive")
        return self


class PageCloneInput(PublicModel):
    source: PageLocator
    destination_slug: Slug
    title: Annotated[str, Field(min_length=1, max_length=500)] | None = None


class CommentCreateInput(PageLocatorInput):
    body: Annotated[str, Field(min_length=1, max_length=WIKI_MAX_COMMENT_CHARS)]
    parent_comment_id: OpaqueID | None = None


class PageRecoverInput(PublicModel):
    recovery_token: OpaqueID


class WikiAttachmentUploadInput(PageLocatorInput):
    file_path: Annotated[str, Field(min_length=1, max_length=4096)]
    append_markup: bool = False
    append_location: Literal["top", "bottom"] = "bottom"


class GridSort(PublicModel):
    column_slug: OpaqueID
    direction: Literal["asc", "desc"]


class GridCreateInput(PageLocatorInput):
    title: Annotated[str, Field(min_length=1, max_length=255)]


class GridUpdateInput(PublicModel):
    grid_id: OpaqueID
    revision: Annotated[int, Field(ge=0)]
    title: Annotated[str, Field(min_length=1, max_length=255)] | None = None
    default_sort: Annotated[list[GridSort], Field(min_length=1, max_length=16)] | None = None

    @model_validator(mode="after")
    def validate_mutable_field(self) -> "GridUpdateInput":
        if self.title is None and self.default_sort is None:
            raise ValueError("title or default_sort is required")
        if self.default_sort and _duplicates([item.column_slug for item in self.default_sort]):
            raise ValueError("default sort columns must be unique")
        return self


class GridCopyInput(PublicModel):
    grid_id: OpaqueID
    destination: PageLocator
    title: Annotated[str, Field(min_length=1, max_length=255)] | None = None


class GridDeleteInput(PublicModel):
    grid_id: OpaqueID
    revision: Annotated[int, Field(ge=0)] | None = None


class GridRowsAddInput(PublicModel):
    grid_id: OpaqueID
    revision: Annotated[int, Field(ge=0)]
    rows: Annotated[list[dict[OpaqueID, JsonScalar]], Field(min_length=1, max_length=1000)]
    position: Annotated[int, Field(ge=0)] | None = None
    after_row_id: OpaqueID | None = None

    @model_validator(mode="after")
    def validate_position(self) -> "GridRowsAddInput":
        if self.position is not None and self.after_row_id is not None:
            raise ValueError("position and after_row_id are mutually exclusive")
        return self


class GridCellUpdate(PublicModel):
    row_id: OpaqueID
    column_id: OpaqueID | None = None
    column_slug: OpaqueID | None = None
    value: JsonScalar

    @model_validator(mode="after")
    def validate_column_locator(self) -> "GridCellUpdate":
        if (self.column_id is None) == (self.column_slug is None):
            raise ValueError("provide exactly one column locator")
        return self


class GridCellsUpdateInput(PublicModel):
    grid_id: OpaqueID
    revision: Annotated[int, Field(ge=0)]
    cells: Annotated[list[GridCellUpdate], Field(min_length=1, max_length=1000)]


class GridRowsDeleteInput(PublicModel):
    grid_id: OpaqueID
    revision: Annotated[int, Field(ge=0)]
    row_ids: Annotated[list[OpaqueID], Field(min_length=1, max_length=1000)]

    @model_validator(mode="after")
    def validate_unique_rows(self) -> "GridRowsDeleteInput":
        if _duplicates(self.row_ids):
            raise ValueError("row IDs must be unique")
        return self


class GridRowMoveInput(PublicModel):
    grid_id: OpaqueID
    revision: Annotated[int, Field(ge=0)]
    row_id: OpaqueID
    position: Annotated[int, Field(ge=0)] | None = None
    after_row_id: OpaqueID | None = None

    @model_validator(mode="after")
    def validate_position(self) -> "GridRowMoveInput":
        if (self.position is None) == (self.after_row_id is None):
            raise ValueError("provide exactly one row position")
        return self


class GridColumnCreate(PublicModel):
    title: Annotated[str, Field(min_length=1, max_length=255)]
    slug: Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9_-]*$")]
    type: Literal["string", "number", "checkbox", "date", "select", "staff"]
    required: bool
    select_options: Annotated[list[str], Field(min_length=1, max_length=100)] | None = None
    multiple: bool | None = None

    @model_validator(mode="after")
    def validate_type_fields(self) -> "GridColumnCreate":
        if self.type == "select":
            if not self.select_options or _duplicates(self.select_options):
                raise ValueError("select columns require unique select_options")
        elif self.select_options is not None:
            raise ValueError("select_options are only valid for select columns")
        if self.type == "staff":
            if self.multiple is None:
                self.multiple = False
        elif self.multiple is not None:
            raise ValueError("multiple is only valid for staff columns")
        return self


class GridColumnsAddInput(PublicModel):
    grid_id: OpaqueID
    revision: Annotated[int, Field(ge=0)]
    columns: Annotated[list[GridColumnCreate], Field(min_length=1, max_length=100)]
    position: Annotated[int, Field(ge=0)] | None = None

    @model_validator(mode="after")
    def validate_unique_slugs(self) -> "GridColumnsAddInput":
        if _duplicates([column.slug for column in self.columns]):
            raise ValueError("column slugs must be unique")
        return self


class GridColumnsDeleteInput(PublicModel):
    grid_id: OpaqueID
    revision: Annotated[int, Field(ge=0)]
    column_slugs: Annotated[list[OpaqueID], Field(min_length=1, max_length=100)]

    @model_validator(mode="after")
    def validate_unique_slugs(self) -> "GridColumnsDeleteInput":
        if _duplicates(self.column_slugs):
            raise ValueError("column slugs must be unique")
        return self


class GridColumnMoveInput(PublicModel):
    grid_id: OpaqueID
    revision: Annotated[int, Field(ge=0)]
    column_slug: OpaqueID
    position: Annotated[int, Field(ge=0)]


class WikiSearchItemWire(WireModel):
    id: int | None = None
    slug: str | None = None
    title: str | None = None
    content: str | None = None
    type: str | None = None
    url: str | None = None
    modified_at: str | None = None


class WikiSearchWire(WireModel):
    results: list[WikiSearchItemWire] = Field(default_factory=list)
    next_cursor: str | None = None
    prev_cursor: str | None = None


class WikiSearchItem(PublicModel):
    id: int | None = None
    slug: str | None = None
    title: str | None = None
    content_excerpt: str | None = None
    type: Literal["page", "file"]
    url: str | None = None
    modified_at: str | None = None


class WikiSearchResponse(PublicModel):
    results: list[WikiSearchItem] = Field(default_factory=list)
    next_cursor: Cursor | None = None
    prev_cursor: Cursor | None = None
    pagination_exhausted: bool = False
    truncated_by_upstream: bool = False
    degraded: bool = False
    search_mode: Literal["full_text", "descendants"] = "full_text"


class WikiUserWire(WireModel):
    id: int | None = None
    username: str | None = None
    display_name: str | None = None


class WikiUser(PublicModel):
    id: int | None = None
    username: str | None = None
    display_name: str | None = None


class WikiPageWire(WireModel):
    id: int
    slug: str | None = None
    title: str | None = None
    content: str | None = None
    url: str | None = None
    page_type: str | None = None
    created_at: str | None = None
    modified_at: str | None = None
    attributes: dict[str, object] | None = None


class WikiPage(PublicModel):
    id: int
    slug: str | None = None
    title: str | None = None
    content: str | None = None
    url: str | None = None
    page_type: str | None = None
    created_at: str | None = None
    modified_at: str | None = None
    attributes: dict[str, JsonScalar] = Field(default_factory=dict)


class DescendantItemWire(WireModel):
    id: int
    slug: str | None = None


class DescendantsWire(WireModel):
    results: list[DescendantItemWire] = Field(default_factory=list)
    next_cursor: str | None = None
    prev_cursor: str | None = None


class DescendantItem(PublicModel):
    id: int
    slug: str | None = None


class DescendantsResponse(PublicModel):
    results: list[DescendantItem] = Field(default_factory=list)
    next_cursor: Cursor | None = None
    prev_cursor: Cursor | None = None
    truncated: bool = False


class PageCommentWire(WireModel):
    id: int
    body: str | None = None
    parent_id: int | None = None
    thread_id: int | None = None
    created_at: str | None = None
    author: WikiUserWire | None = None
    inline_text: str | None = None
    is_deleted: bool | None = None
    resolve_status: str | None = None


class CommentsWire(WireModel):
    results: list[PageCommentWire] = Field(default_factory=list)
    next_cursor: str | None = None
    prev_cursor: str | None = None


class PageComment(PublicModel):
    id: int
    body: str | None = None
    parent_id: int | None = None
    thread_id: int | None = None
    created_at: str | None = None
    author: WikiUser | None = None
    inline_text: str | None = None
    is_deleted: bool | None = None
    resolve_status: str | None = None


class CommentsResponse(PublicModel):
    results: list[PageComment] = Field(default_factory=list)
    next_cursor: Cursor | None = None
    prev_cursor: Cursor | None = None
    truncated: bool = False


class WikiAttachmentWire(WireModel):
    id: int
    name: str | None = None
    size: int | str | None = None
    description: str | None = None
    mime_type: str | None = Field(
        default=None, validation_alias=AliasChoices("mimetype", "mime_type")
    )
    created_at: str | None = None
    has_preview: bool | None = None
    check_status: str | None = None
    is_downloadable: bool | None = None
    user: WikiUserWire | None = None
    download_url: str | None = None


class WikiAttachment(PublicModel):
    id: int
    name: str | None = None
    size: int | None = None
    description: str | None = None
    mime_type: str | None = None
    created_at: str | None = None
    has_preview: bool | None = None
    check_status: str | None = None
    is_downloadable: bool | None = None
    user: WikiUser | None = None


class AttachmentsWire(WireModel):
    results: list[WikiAttachmentWire] = Field(default_factory=list)
    next_cursor: str | None = None
    prev_cursor: str | None = None


class AttachmentsResponse(PublicModel):
    results: list[WikiAttachment] = Field(default_factory=list)
    next_cursor: Cursor | None = None
    prev_cursor: Cursor | None = None
    truncated: bool = False


class WikiGridSummaryWire(WireModel):
    id: str | int
    title: str | None = None
    created_at: str | None = None


class WikiGridSummary(PublicModel):
    id: str | int
    title: str | None = None
    created_at: str | None = None


class GridSortWire(WireModel):
    column_slug: str = Field(validation_alias=AliasChoices("slug", "column_slug"))
    direction: str


class WikiGridColumnWire(WireModel):
    id: str | None = None
    slug: str | None = None
    title: str | None = None
    type: str | None = None
    required: bool | None = None
    multiple: bool | None = None
    select_options: list[str] | None = None


class WikiGridColumn(PublicModel):
    id: str | None = None
    slug: str | None = None
    title: str | None = None
    type: Literal["string", "number", "checkbox", "date", "select", "staff"] | None = None
    required: bool | None = None
    multiple: bool | None = None
    select_options: list[str] | None = None


class WikiGridRowWire(WireModel):
    id: str | int | None = None
    cells: dict[str, object] | None = None
    row: list[object] | None = None
    pinned: bool | None = None
    color: str | None = None


class WikiGridRow(PublicModel):
    id: str | int | None = None
    cells: dict[str, JsonScalar] = Field(default_factory=dict)
    pinned: bool | None = None
    color: str | None = None


class WikiGridPageWire(WireModel):
    id: str | int | None = None
    slug: str | None = None


class WikiGridPage(PublicModel):
    id: str | int | None = None
    slug: str | None = None


class WikiGridStructureWire(WireModel):
    columns: list[WikiGridColumnWire] = Field(default_factory=list)
    default_sort: list[GridSortWire] = Field(default_factory=list)


class WikiGridWire(WireModel):
    id: str | int
    title: str | None = None
    page: WikiGridPageWire = Field(default_factory=WikiGridPageWire)
    revision: str | int | None = None
    structure: WikiGridStructureWire | None = None
    columns: list[WikiGridColumnWire] = Field(default_factory=list)
    rows: list[WikiGridRowWire] = Field(default_factory=list)
    default_sort: list[GridSortWire] = Field(default_factory=list)
    created_at: str | None = None


class WikiGrid(PublicModel):
    id: str | int
    title: str | None = None
    page: WikiGridPage = Field(default_factory=WikiGridPage)
    revision: str | None = None
    columns: list[WikiGridColumn] = Field(default_factory=list)
    rows: list[WikiGridRow] = Field(default_factory=list)
    default_sort: list[GridSort] = Field(default_factory=list)
    created_at: str | None = None


class GridsWire(WireModel):
    results: list[WikiGridSummaryWire] = Field(default_factory=list)
    next_cursor: str | None = None
    prev_cursor: str | None = None


class GridsResponse(PublicModel):
    results: list[WikiGridSummary] = Field(default_factory=list)
    next_cursor: Cursor | None = None
    prev_cursor: Cursor | None = None
    truncated: bool = False


class WikiResourceWire(WireModel):
    type: str
    item: dict[str, object]


class WikiResource(PublicModel):
    type: Literal["attachment", "grid"]
    item: WikiAttachment | WikiGridSummary

    @model_validator(mode="after")
    def validate_item_type(self) -> "WikiResource":
        expected = WikiAttachment if self.type == "attachment" else WikiGridSummary
        if not isinstance(self.item, expected):
            raise TypeError("resource type does not match item")
        return self


class ResourcesWire(WireModel):
    results: list[WikiResourceWire] = Field(default_factory=list)
    next_cursor: str | None = None
    prev_cursor: str | None = None


class ResourcesResponse(PublicModel):
    results: list[WikiResource] = Field(default_factory=list)
    next_cursor: Cursor | None = None
    prev_cursor: Cursor | None = None
    truncated: bool = False


class PageCloneWire(WireModel):
    id: int
    slug: str


class PageCloneResponse(PublicModel):
    id: int
    slug: str
    status: Literal["completed"] = "completed"


class PageDeleteResponse(PublicModel):
    deleted: Literal[True] = True
    recovery_token: str | None = None


class PageDeleteWire(WireModel):
    recovery_token: str


class PageRecoverWire(WireModel):
    id: int
    slug: str | None = None
    pages_count: int | None = None


class PageRecoverResponse(PublicModel):
    id: int
    slug: str | None = None
    pages_count: Annotated[int, Field(ge=1)] | None = None
    status: Literal["completed"] = "completed"


class AttachmentUploadResponse(PublicModel):
    page_id: int
    attachments: list[WikiAttachment]
    appended_markup: bool = False
    appended_content: str | None = None


class GridUpdateWire(WireModel):
    revision: str | int
    warnings: list[str] = Field(default_factory=list)


class GridOperationIdentityWire(WireModel):
    type: Literal["clone", "clone_inline_grid"]
    id: str


class GridCopyWire(WireModel):
    operation: GridOperationIdentityWire
    status_url: str
    dry_run: bool = False
    warnings: list[str] = Field(default_factory=list)


class GridUpdateResponse(PublicModel):
    grid: WikiGrid
    warnings: list[str] = Field(default_factory=list)


class GridMutationWire(WireModel):
    revision: str | int | None = None
    results: list[WikiGridRowWire] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class GridMutationResponse(PublicModel):
    revision: str | None = None
    results: list[WikiGridRow] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class GridCellWire(WireModel):
    row_id: str | int
    column_id: str | None = None
    column_slug: str | None = None
    value: object = None


class GridCell(PublicModel):
    row_id: str | int
    column_id: str | None = None
    column_slug: str | None = None
    value: JsonScalar

    @model_validator(mode="after")
    def validate_column_locator(self) -> "GridCell":
        if (self.column_id is None) == (self.column_slug is None):
            raise ValueError("provide exactly one column locator")
        return self


class GridCellsWire(WireModel):
    revision: str | int | None = None
    cells: list[GridCellWire] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class GridCellsResponse(PublicModel):
    revision: str | None = None
    cells: list[GridCell] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class GridOperationResponse(PublicModel):
    status: Literal["completed", "pending"]
    operation_id: str | None = None
    grid: WikiGridSummary | None = None
    warnings: list[str] = Field(default_factory=list)


class GridDeleteResponse(PublicModel):
    grid_id: str
    deleted: Literal[True] = True


def _is_scalar(value: object) -> TypeGuard[JsonScalar]:
    return (
        value is None
        or isinstance(value, (str, bool, int))
        or (isinstance(value, float) and math.isfinite(value))
    )


def _scalar_dict(values: dict[str, object] | None) -> dict[str, JsonScalar]:
    return {key: value for key, value in (values or {}).items() if _is_scalar(value)}  # type: ignore[misc]


def _optional_string(value: JsonScalar) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(value: int | str | None) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdecimal():
        return int(value)
    return None


def map_wiki_user(wire: WikiUserWire | None) -> WikiUser | None:
    if wire is None:
        return None
    return WikiUser(id=wire.id, username=wire.username, display_name=wire.display_name)


def map_wiki_search(wire: WikiSearchWire) -> WikiSearchResponse:
    return WikiSearchResponse(
        results=[
            WikiSearchItem(
                id=item.id,
                slug=item.slug,
                title=item.title,
                content_excerpt=item.content,
                type="file" if item.type == "file" else "page",
                url=item.url,
                modified_at=item.modified_at,
            )
            for item in wire.results
        ],
        next_cursor=wire.next_cursor,
        prev_cursor=wire.prev_cursor,
    )


def map_wiki_page(wire: WikiPageWire) -> WikiPage:
    attributes = _scalar_dict(wire.attributes)
    return WikiPage(
        id=wire.id,
        slug=wire.slug,
        title=wire.title,
        content=wire.content,
        url=wire.url,
        page_type=wire.page_type,
        created_at=wire.created_at or _optional_string(attributes.get("created_at")),
        modified_at=wire.modified_at or _optional_string(attributes.get("modified_at")),
        attributes=attributes,
    )


def map_descendants(wire: DescendantsWire) -> DescendantsResponse:
    return DescendantsResponse(
        results=[DescendantItem(id=item.id, slug=item.slug) for item in wire.results],
        next_cursor=wire.next_cursor,
        prev_cursor=wire.prev_cursor,
    )


def map_comment(wire: PageCommentWire) -> PageComment:
    return PageComment(
        id=wire.id,
        body=wire.body,
        parent_id=wire.parent_id,
        thread_id=wire.thread_id,
        created_at=wire.created_at,
        author=map_wiki_user(wire.author),
        inline_text=wire.inline_text,
        is_deleted=wire.is_deleted,
        resolve_status=wire.resolve_status,
    )


def map_comments(wire: CommentsWire) -> CommentsResponse:
    return CommentsResponse(
        results=[map_comment(item) for item in wire.results],
        next_cursor=wire.next_cursor,
        prev_cursor=wire.prev_cursor,
    )


def map_attachment(wire: WikiAttachmentWire) -> WikiAttachment:
    return WikiAttachment(
        id=wire.id,
        name=wire.name,
        size=_optional_int(wire.size),
        description=wire.description,
        mime_type=wire.mime_type,
        created_at=wire.created_at,
        has_preview=wire.has_preview,
        check_status=wire.check_status,
        is_downloadable=wire.is_downloadable,
        user=map_wiki_user(wire.user),
    )


def map_attachments(wire: AttachmentsWire) -> AttachmentsResponse:
    return AttachmentsResponse(
        results=[map_attachment(item) for item in wire.results],
        next_cursor=wire.next_cursor,
        prev_cursor=wire.prev_cursor,
    )


def map_grid_summary(wire: WikiGridSummaryWire) -> WikiGridSummary:
    return WikiGridSummary(id=wire.id, title=wire.title, created_at=wire.created_at)


def map_grid_row(wire: WikiGridRowWire) -> WikiGridRow:
    return WikiGridRow(
        id=wire.id,
        cells=_scalar_dict(wire.cells),
        pinned=wire.pinned,
        color=wire.color,
    )


def map_grid(wire: WikiGridWire) -> WikiGrid:
    valid_types = {"string", "number", "checkbox", "date", "select", "staff"}
    columns = wire.structure.columns if wire.structure is not None else wire.columns
    default_sort = wire.structure.default_sort if wire.structure is not None else wire.default_sort
    public_columns = [
        WikiGridColumn(
            id=item.id,
            slug=item.slug,
            title=item.title,
            type=item.type if item.type in valid_types else None,  # type: ignore[arg-type]
            required=item.required,
            multiple=item.multiple,
            select_options=item.select_options,
        )
        for item in columns
    ]
    public_rows: list[WikiGridRow] = []
    for row in wire.rows:
        if row.cells is not None:
            public_rows.append(map_grid_row(row))
            continue
        cells = {
            column.slug: value
            for column, value in zip(public_columns, row.row or [], strict=False)
            if column.slug is not None and _is_scalar(value)
        }
        public_rows.append(WikiGridRow(id=row.id, cells=cells, pinned=row.pinned, color=row.color))
    return WikiGrid(
        id=wire.id,
        title=wire.title,
        page=WikiGridPage(id=wire.page.id, slug=wire.page.slug),
        revision=str(wire.revision) if wire.revision is not None else None,
        columns=public_columns,
        rows=public_rows,
        default_sort=[
            GridSort(column_slug=item.column_slug, direction=item.direction)  # type: ignore[arg-type]
            for item in default_sort
            if item.direction in {"asc", "desc"}
        ],
        created_at=wire.created_at,
    )


def map_grids(wire: GridsWire) -> GridsResponse:
    return GridsResponse(
        results=[map_grid_summary(item) for item in wire.results],
        next_cursor=wire.next_cursor,
        prev_cursor=wire.prev_cursor,
    )


def map_resources(wire: ResourcesWire) -> ResourcesResponse:
    results: list[WikiResource] = []
    for resource in wire.results:
        if resource.type == "attachment":
            attachment = map_attachment(WikiAttachmentWire.model_validate(resource.item))
            results.append(WikiResource(type="attachment", item=attachment))
        elif resource.type == "grid":
            grid = map_grid_summary(WikiGridSummaryWire.model_validate(resource.item))
            results.append(WikiResource(type="grid", item=grid))
    return ResourcesResponse(
        results=results,
        next_cursor=wire.next_cursor,
        prev_cursor=wire.prev_cursor,
    )


def map_grid_update(wire: GridUpdateWire, grid: WikiGrid) -> GridUpdateResponse:
    return GridUpdateResponse(grid=grid, warnings=list(wire.warnings))


def map_grid_mutation(wire: GridMutationWire) -> GridMutationResponse:
    return GridMutationResponse(
        revision=str(wire.revision) if wire.revision is not None else None,
        results=[map_grid_row(item) for item in wire.results],
        warnings=list(wire.warnings),
    )


def map_grid_cells(wire: GridCellsWire) -> GridCellsResponse:
    cells: list[GridCell] = []
    for item in wire.cells:
        if not _is_scalar(item.value) or ((item.column_id is None) == (item.column_slug is None)):
            continue
        cells.append(
            GridCell(
                row_id=item.row_id,
                column_id=item.column_id,
                column_slug=item.column_slug,
                value=item.value,  # type: ignore[arg-type]
            )
        )
    return GridCellsResponse(
        revision=str(wire.revision) if wire.revision is not None else None,
        cells=cells,
        warnings=list(wire.warnings),
    )

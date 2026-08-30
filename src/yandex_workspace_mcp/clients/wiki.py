import urllib.parse
from collections.abc import Awaitable, Callable
from json import JSONDecodeError
from typing import Any

import httpx
from pydantic import ValidationError

from ..models.errors import ContractMismatchError, ResourceNotFound
from ..models.wiki import (
    AttachmentsResponse,
    AttachmentsWire,
    AttachmentUploadResponse,
    CommentCreateInput,
    CommentsResponse,
    CommentsWire,
    DescendantsInput,
    DescendantsResponse,
    DescendantsWire,
    GridCellsResponse,
    GridCellsUpdateInput,
    GridCellsWire,
    GridColumnMoveInput,
    GridColumnsAddInput,
    GridColumnsDeleteInput,
    GridCopyWire,
    GridCreateInput,
    GridDeleteInput,
    GridDeleteResponse,
    GridGetInput,
    GridMutationResponse,
    GridMutationWire,
    GridOperationResponse,
    GridRowMoveInput,
    GridRowsAddInput,
    GridRowsDeleteInput,
    GridsResponse,
    GridsWire,
    GridUpdateInput,
    GridUpdateResponse,
    GridUpdateWire,
    PageAppendInput,
    PageCloneInput,
    PageCloneResponse,
    PageCloneWire,
    PageComment,
    PageCommentWire,
    PageCreateInput,
    PageDeleteWire,
    PageListInput,
    PageLocator,
    PageRecoverResponse,
    PageRecoverWire,
    PageResourceListInput,
    PageUpdateInput,
    ResourcesResponse,
    ResourcesWire,
    WikiAttachmentUploadInput,
    WikiGrid,
    WikiGridWire,
    WikiPage,
    WikiPageWire,
    WikiSearchInput,
    WikiSearchResponse,
    WikiSearchWire,
    map_attachments,
    map_comment,
    map_comments,
    map_descendants,
    map_grid,
    map_grid_cells,
    map_grid_mutation,
    map_grid_update,
    map_grids,
    map_resources,
    map_wiki_page,
    map_wiki_search,
)
from ..policies.local_files import AllowedLocalFile
from ..policies.urls import poll_operation, validate_operation_url
from .base import BaseYandexClient, RequestCredentials, RequestSemantics
from .signed import SignedTransferClient


class SearchFilterUnsupported(ContractMismatchError):
    pass


class SearchUnavailable(ResourceNotFound):
    pass


class YandexWikiClient(BaseYandexClient):
    PAGE_FIELDS = "content,attributes"

    def __init__(
        self,
        token: str | None = None,
        org_id: str | None = None,
        is_cloud_org: bool = False,
        *,
        client: httpx.AsyncClient | None = None,
        credential_provider: Callable[[], Awaitable[RequestCredentials]] | None = None,
    ) -> None:
        headers: dict[str, str] = {}
        if org_id:
            headers["X-Cloud-Org-Id" if is_cloud_org else "X-Org-Id"] = org_id
        super().__init__(
            token,
            base_url="https://api.wiki.yandex.net/v1",
            headers=headers,
            client=client,
            credential_provider=credential_provider,
        )

    async def search(
        self,
        search_input: WikiSearchInput,
        *,
        cluster: str | None = None,
        credentials: RequestCredentials | None = None,
    ) -> WikiSearchResponse:
        if search_input.page > 5:
            return WikiSearchResponse(pagination_exhausted=True)

        upstream_limit = min(50, search_input.page * search_input.limit)
        payload: dict[str, Any] = {
            "query": search_input.query,
            "limit": upstream_limit,
        }
        if cluster is not None:
            payload["filters"] = {"cluster": cluster}
        response = await self._request(
            "POST",
            "/search",
            semantics=RequestSemantics.LOGICAL_READ,
            credentials=credentials,
            translate_errors=False,
            json=payload,
        )
        self._classify_search_error(response, filtered=cluster is not None)
        try:
            wire = WikiSearchWire.model_validate(response.json())
        except (ValidationError, JSONDecodeError, ValueError, TypeError) as exc:
            raise ContractMismatchError() from exc
        public = map_wiki_search(wire)
        if search_input.page > 1:
            start = (search_input.page - 1) * search_input.limit
            public = public.model_copy(
                update={"results": public.results[start : start + search_input.limit]}
            )
        return public

    @classmethod
    def _classify_search_error(cls, response: httpx.Response, *, filtered: bool) -> None:
        if response.status_code < 400:
            return
        if response.status_code in {404, 405, 410}:
            raise SearchUnavailable()
        if response.status_code == 400 and filtered:
            try:
                payload = response.json()
            except (JSONDecodeError, ValueError):
                payload = {}
            code = str(payload.get("code", "")).upper() if isinstance(payload, dict) else ""
            message = (
                str(payload.get("message", "")).casefold() if isinstance(payload, dict) else ""
            )
            if code in {"UNKNOWN_FIELD", "VALIDATION_ERROR"} and "filter" in message:
                raise SearchFilterUnsupported()
        cls._raise_for_status(response)

    async def get_page(
        self,
        locator: PageLocator | str,
        *,
        credentials: RequestCredentials | None = None,
    ) -> WikiPage:
        if isinstance(locator, str):
            locator = PageLocator(slug=locator)
        if locator.page_id is not None:
            path = f"/pages/{locator.page_id}"
            params: dict[str, str] = {"fields": self.PAGE_FIELDS}
        else:
            path = "/pages"
            slug = locator.slug or self._slug_from_url(locator.url or "")
            params = {"slug": slug, "fields": self.PAGE_FIELDS}
        response = await self._request(
            "GET",
            path,
            semantics=RequestSemantics.SAFE_READ,
            credentials=credentials,
            params=params,
        )
        try:
            return map_wiki_page(WikiPageWire.model_validate(response.json()))
        except (ValidationError, JSONDecodeError, ValueError, TypeError) as exc:
            raise ContractMismatchError() from exc

    async def get_descendants(
        self,
        descendants_input: DescendantsInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> DescendantsResponse:
        locator = descendants_input.locator
        params: dict[str, str | int | bool] = {
            "page_size": descendants_input.page_size,
            "include_self": descendants_input.include_self,
        }
        if locator.page_id is not None:
            path = f"/pages/{locator.page_id}/descendants"
        else:
            path = "/pages/descendants"
            params["slug"] = locator.slug or self._slug_from_url(locator.url or "")
        if descendants_input.cursor:
            params["cursor"] = descendants_input.cursor
        response = await self._request(
            "GET",
            path,
            semantics=RequestSemantics.SAFE_READ,
            credentials=credentials,
            params=params,
        )
        try:
            return map_descendants(DescendantsWire.model_validate(response.json()))
        except (ValidationError, JSONDecodeError, ValueError, TypeError) as exc:
            raise ContractMismatchError() from exc

    async def get_comments(
        self,
        page_input: PageListInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> CommentsResponse:
        page_id = await self._resolve_page_id(page_input.locator, credentials)
        response = await self._page_collection_request(
            f"/pages/{page_id}/comments", page_input, credentials=credentials
        )
        if not response.content:
            return CommentsResponse()
        try:
            return map_comments(CommentsWire.model_validate(response.json()))
        except (ValidationError, JSONDecodeError, ValueError, TypeError) as exc:
            raise ContractMismatchError() from exc

    async def get_resources(
        self,
        page_input: PageResourceListInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> ResourcesResponse:
        page_id = await self._resolve_page_id(page_input.locator, credentials)
        params = self._page_collection_params(page_input)
        if page_input.resource_types:
            params["types"] = ",".join(page_input.resource_types)
        response = await self._request(
            "GET",
            f"/pages/{page_id}/resources",
            semantics=RequestSemantics.SAFE_READ,
            credentials=credentials,
            params=params,
        )
        if not response.content:
            return ResourcesResponse()
        try:
            return map_resources(ResourcesWire.model_validate(response.json()))
        except (ValidationError, JSONDecodeError, ValueError, TypeError) as exc:
            raise ContractMismatchError() from exc

    async def get_attachments(
        self,
        page_input: PageListInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> AttachmentsResponse:
        page_id = await self._resolve_page_id(page_input.locator, credentials)
        response = await self._page_collection_request(
            f"/pages/{page_id}/attachments", page_input, credentials=credentials
        )
        if not response.content:
            return AttachmentsResponse()
        try:
            return map_attachments(AttachmentsWire.model_validate(response.json()))
        except (ValidationError, JSONDecodeError, ValueError, TypeError) as exc:
            raise ContractMismatchError() from exc

    async def get_grids(
        self,
        page_input: PageListInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> GridsResponse:
        page_id = await self._resolve_page_id(page_input.locator, credentials)
        response = await self._page_collection_request(
            f"/pages/{page_id}/grids", page_input, credentials=credentials
        )
        if not response.content:
            return GridsResponse()
        try:
            return map_grids(GridsWire.model_validate(response.json()))
        except (ValidationError, JSONDecodeError, ValueError, TypeError) as exc:
            raise ContractMismatchError() from exc

    async def get_grid(
        self,
        grid_input: GridGetInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> WikiGrid:
        params: dict[str, str | int] = {"fields": "attributes"}
        if grid_input.revision is not None:
            params["revision"] = grid_input.revision
        if grid_input.row_ids:
            params["only_rows"] = ",".join(grid_input.row_ids)
        if grid_input.column_slugs:
            params["only_cols"] = ",".join(grid_input.column_slugs)
        response = await self._request(
            "GET",
            f"/grids/{grid_input.grid_id}",
            semantics=RequestSemantics.SAFE_READ,
            credentials=credentials,
            params=params,
        )
        try:
            return map_grid(WikiGridWire.model_validate(response.json()))
        except (ValidationError, JSONDecodeError, ValueError, TypeError) as exc:
            raise ContractMismatchError() from exc

    async def create_grid(
        self,
        page_id: int,
        grid_input: GridCreateInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> WikiGrid:
        response = await self._request(
            "POST",
            "/grids",
            semantics=RequestSemantics.MUTATION,
            credentials=credentials,
            json={"title": grid_input.title, "page": {"id": page_id}},
        )
        return self._parse_grid(response)

    async def update_grid(
        self,
        grid_input: GridUpdateInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> GridUpdateResponse:
        payload: dict[str, object] = {"revision": grid_input.revision}
        if grid_input.title is not None:
            payload["title"] = grid_input.title
        if grid_input.default_sort is not None:
            payload["default_sort"] = {
                item.column_slug: item.direction for item in grid_input.default_sort
            }
        response = await self._request(
            "POST",
            f"/grids/{grid_input.grid_id}",
            semantics=RequestSemantics.MUTATION,
            credentials=credentials,
            json=payload,
        )
        try:
            wire = GridUpdateWire.model_validate(response.json())
        except (ValidationError, JSONDecodeError, ValueError, TypeError) as exc:
            raise ContractMismatchError() from exc
        revision_text = str(wire.revision)
        revision = int(revision_text) if revision_text.isdecimal() else None
        grid = await self.get_grid(
            GridGetInput(grid_id=grid_input.grid_id, revision=revision),
            credentials=credentials,
        )
        return map_grid_update(wire, grid)

    async def copy_grid(
        self,
        grid_id: str,
        *,
        destination_slug: str,
        title: str | None = None,
        credentials: RequestCredentials | None = None,
    ) -> GridOperationResponse:
        payload: dict[str, object] = {
            "target": destination_slug,
            "with_data": False,
        }
        if title is not None:
            payload["title"] = title
        response = await self._request(
            "POST",
            f"/grids/{grid_id}/clone",
            semantics=RequestSemantics.MUTATION,
            credentials=credentials,
            json=payload,
        )
        try:
            wire = GridCopyWire.model_validate(response.json())
        except (ValidationError, JSONDecodeError, ValueError, TypeError) as exc:
            raise ContractMismatchError() from exc
        validate_operation_url(wire.status_url)
        return GridOperationResponse(
            status="pending",
            operation_id=wire.operation.id,
            warnings=list(wire.warnings),
        )

    async def delete_grid(
        self,
        grid_input: GridDeleteInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> GridDeleteResponse:
        response = await self._request(
            "DELETE",
            f"/grids/{grid_input.grid_id}",
            semantics=RequestSemantics.MUTATION,
            credentials=credentials,
        )
        if response.status_code != 204 or response.content:
            raise ContractMismatchError()
        return GridDeleteResponse(grid_id=grid_input.grid_id)

    async def add_grid_rows(
        self,
        grid_input: GridRowsAddInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> GridMutationResponse:
        payload: dict[str, object] = {
            "revision": grid_input.revision,
            "rows": grid_input.rows,
        }
        if grid_input.position is not None:
            payload["position"] = grid_input.position
        if grid_input.after_row_id is not None:
            payload["after_row_id"] = grid_input.after_row_id
        return await self._grid_mutation(
            "POST",
            f"/grids/{grid_input.grid_id}/rows",
            payload,
            credentials=credentials,
        )

    async def update_grid_cells(
        self,
        grid_input: GridCellsUpdateInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> GridCellsResponse:
        response = await self._request(
            "POST",
            f"/grids/{grid_input.grid_id}/cells",
            semantics=RequestSemantics.MUTATION,
            credentials=credentials,
            json={
                "revision": grid_input.revision,
                "cells": [
                    {
                        "row_id": cell.row_id,
                        **(
                            {"column_id": cell.column_id}
                            if cell.column_id is not None
                            else {"column_slug": cell.column_slug}
                        ),
                        "value": cell.value,
                    }
                    for cell in grid_input.cells
                ],
            },
        )
        try:
            return map_grid_cells(GridCellsWire.model_validate(response.json()))
        except (ValidationError, JSONDecodeError, ValueError, TypeError) as exc:
            raise ContractMismatchError() from exc

    async def delete_grid_rows(
        self,
        grid_input: GridRowsDeleteInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> GridMutationResponse:
        return await self._grid_mutation(
            "DELETE",
            f"/grids/{grid_input.grid_id}/rows",
            {"revision": grid_input.revision, "row_ids": grid_input.row_ids},
            credentials=credentials,
        )

    async def move_grid_row(
        self,
        grid_input: GridRowMoveInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> GridMutationResponse:
        payload: dict[str, object] = {
            "revision": grid_input.revision,
            "row_id": grid_input.row_id,
        }
        if grid_input.position is not None:
            payload["position"] = grid_input.position
        if grid_input.after_row_id is not None:
            payload["after_row_id"] = grid_input.after_row_id
        return await self._grid_mutation(
            "POST",
            f"/grids/{grid_input.grid_id}/rows/move",
            payload,
            credentials=credentials,
        )

    async def add_grid_columns(
        self,
        grid_input: GridColumnsAddInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> GridMutationResponse:
        payload: dict[str, object] = {
            "revision": grid_input.revision,
            "columns": [
                column.model_dump(mode="json", exclude_none=True) for column in grid_input.columns
            ],
        }
        if grid_input.position is not None:
            payload["position"] = grid_input.position
        return await self._grid_mutation(
            "POST",
            f"/grids/{grid_input.grid_id}/columns",
            payload,
            credentials=credentials,
        )

    async def delete_grid_columns(
        self,
        grid_input: GridColumnsDeleteInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> GridMutationResponse:
        return await self._grid_mutation(
            "DELETE",
            f"/grids/{grid_input.grid_id}/columns",
            {
                "revision": grid_input.revision,
                "column_slugs": grid_input.column_slugs,
            },
            credentials=credentials,
        )

    async def move_grid_column(
        self,
        grid_input: GridColumnMoveInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> GridMutationResponse:
        return await self._grid_mutation(
            "POST",
            f"/grids/{grid_input.grid_id}/columns/move",
            {
                "revision": grid_input.revision,
                "column_slug": grid_input.column_slug,
                "position": grid_input.position,
            },
            credentials=credentials,
        )

    async def _grid_mutation(
        self,
        method: str,
        path: str,
        payload: dict[str, object],
        *,
        credentials: RequestCredentials | None,
    ) -> GridMutationResponse:
        response = await self._request(
            method,
            path,
            semantics=RequestSemantics.MUTATION,
            credentials=credentials,
            json=payload,
        )
        try:
            return map_grid_mutation(GridMutationWire.model_validate(response.json()))
        except (ValidationError, JSONDecodeError, ValueError, TypeError) as exc:
            raise ContractMismatchError() from exc

    async def create_page(
        self,
        page_input: PageCreateInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> WikiPage:
        response = await self._request(
            "POST",
            "/pages",
            semantics=RequestSemantics.MUTATION,
            credentials=credentials,
            params={"fields": self.PAGE_FIELDS},
            json=page_input.model_dump(mode="json"),
        )
        return self._parse_page(response)

    async def update_page(
        self,
        page_id: int,
        page_input: PageUpdateInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> WikiPage:
        payload = {
            key: value
            for key, value in {
                "title": page_input.title,
                "content": page_input.content,
            }.items()
            if value is not None
        }
        response = await self._request(
            "POST",
            f"/pages/{page_id}",
            semantics=RequestSemantics.MUTATION,
            credentials=credentials,
            params={
                "allow_merge": page_input.allow_merge,
                "is_silent": page_input.is_silent,
                "fields": self.PAGE_FIELDS,
            },
            json=payload,
        )
        return self._parse_page(response)

    async def append_page(
        self,
        page_id: int,
        page_input: PageAppendInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> WikiPage:
        payload: dict[str, object] = {"content": page_input.content}
        if page_input.anchor is not None:
            payload["anchor"] = {"name": page_input.anchor}
        else:
            payload["body"] = {"location": page_input.location}
        response = await self._request(
            "POST",
            f"/pages/{page_id}/append-content",
            semantics=RequestSemantics.MUTATION,
            credentials=credentials,
            params={"fields": self.PAGE_FIELDS},
            json=payload,
        )
        return self._parse_page(response)

    async def clone_page(
        self,
        page_id: int,
        page_input: PageCloneInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> PageCloneResponse:
        payload: dict[str, object] = {
            "target": page_input.destination_slug,
            "subscribe_me": False,
        }
        if page_input.title is not None:
            payload["title"] = page_input.title
        response = await self._request(
            "POST",
            f"/pages/{page_id}/clone",
            semantics=RequestSemantics.MUTATION,
            credentials=credentials,
            json=payload,
        )
        try:
            start = response.json()
            if not isinstance(start, dict) or not isinstance(start.get("status_url"), str):
                raise ContractMismatchError()
            status_url = validate_operation_url(start["status_url"])
        except (JSONDecodeError, ValueError, TypeError) as exc:
            raise ContractMismatchError() from exc
        completed = await poll_operation(
            self,
            status_url,
            credentials=credentials,
        )
        result = completed.get("result")
        if not isinstance(result, dict):
            raise ContractMismatchError()
        page = result.get("page", result)
        try:
            wire = PageCloneWire.model_validate(page)
        except (ValidationError, ValueError, TypeError) as exc:
            raise ContractMismatchError() from exc
        return PageCloneResponse(id=wire.id, slug=wire.slug)

    async def add_comment(
        self,
        page_id: int,
        comment_input: CommentCreateInput,
        *,
        credentials: RequestCredentials | None = None,
    ) -> PageComment:
        payload: dict[str, object] = {"body": comment_input.body}
        if comment_input.parent_comment_id is not None:
            payload["parent_id"] = comment_input.parent_comment_id
        response = await self._request(
            "POST",
            f"/pages/{page_id}/comments",
            semantics=RequestSemantics.MUTATION,
            credentials=credentials,
            json=payload,
        )
        try:
            return map_comment(PageCommentWire.model_validate(response.json()))
        except (ValidationError, JSONDecodeError, ValueError, TypeError) as exc:
            raise ContractMismatchError() from exc

    async def delete_page(
        self,
        page_id: int,
        *,
        credentials: RequestCredentials | None = None,
    ) -> str:
        response = await self._request(
            "DELETE",
            f"/pages/{page_id}",
            semantics=RequestSemantics.MUTATION,
            credentials=credentials,
        )
        try:
            return PageDeleteWire.model_validate(response.json()).recovery_token
        except (ValidationError, JSONDecodeError, ValueError, TypeError) as exc:
            raise ContractMismatchError() from exc

    async def recover_page(
        self,
        upstream_token: str,
        *,
        credentials: RequestCredentials | None = None,
    ) -> PageRecoverResponse:
        response = await self._request(
            "POST",
            f"/recovery_tokens/{upstream_token}/recover",
            semantics=RequestSemantics.MUTATION,
            credentials=credentials,
        )
        try:
            wire = PageRecoverWire.model_validate(response.json())
        except (ValidationError, JSONDecodeError, ValueError, TypeError) as exc:
            raise ContractMismatchError() from exc
        return PageRecoverResponse(
            id=wire.id,
            slug=wire.slug,
            pages_count=wire.pages_count,
        )

    async def upload_attachment(
        self,
        page_id: int,
        opened: AllowedLocalFile,
        upload_input: WikiAttachmentUploadInput,
        *,
        signed_client: SignedTransferClient | None = None,
        credentials: RequestCredentials | None = None,
    ) -> AttachmentUploadResponse:
        opened.verify_identity()
        response = await self._request(
            "POST",
            "/upload_sessions",
            semantics=RequestSemantics.MUTATION,
            credentials=credentials,
            json={"file_name": opened.basename, "file_size": opened.size},
        )
        try:
            session = response.json()
            session_id = session.get("session_id") if isinstance(session, dict) else None
            upload_url = session.get("upload_url") if isinstance(session, dict) else None
            if not isinstance(session_id, str) or not session_id:
                raise ContractMismatchError()
        except (JSONDecodeError, ValueError, TypeError) as exc:
            raise ContractMismatchError() from exc

        if isinstance(upload_url, str):
            if signed_client is None:
                raise ContractMismatchError()
            await signed_client.upload(upload_url, opened)
        else:
            opened.seek(0)
            part_number = 1
            while chunk := opened.read(5 * 1024 * 1024):
                await self._request(
                    "PUT",
                    f"/upload_sessions/{session_id}/upload_part",
                    semantics=RequestSemantics.SIGNED_UPLOAD,
                    credentials=credentials,
                    params={"part_number": part_number},
                    content=chunk,
                    headers={"Content-Type": "application/octet-stream"},
                )
                part_number += 1

        await self._request(
            "POST",
            f"/upload_sessions/{session_id}/finish",
            semantics=RequestSemantics.MUTATION,
            credentials=credentials,
        )
        attached_response = await self._request(
            "POST",
            f"/pages/{page_id}/attachments",
            semantics=RequestSemantics.MUTATION,
            credentials=credentials,
            json={"upload_sessions": [session_id]},
        )
        try:
            wire = AttachmentsWire.model_validate(attached_response.json())
        except (ValidationError, JSONDecodeError, ValueError, TypeError) as exc:
            raise ContractMismatchError() from exc
        public = map_attachments(wire)
        appended_content: str | None = None
        if upload_input.append_markup and wire.results:
            safe_path = urllib.parse.urlsplit(wire.results[0].download_url or "").path
            appended_content = f'{{% file src="{safe_path}" name="{opened.basename}" %}}'
            await self.append_page(
                page_id,
                PageAppendInput(
                    locator=PageLocator(page_id=page_id),
                    content=appended_content,
                    location=upload_input.append_location,
                ),
                credentials=credentials,
            )
        return AttachmentUploadResponse(
            page_id=page_id,
            attachments=public.results,
            appended_markup=upload_input.append_markup and bool(wire.results),
            appended_content=appended_content,
        )

    @staticmethod
    def _parse_page(response: httpx.Response) -> WikiPage:
        try:
            return map_wiki_page(WikiPageWire.model_validate(response.json()))
        except (ValidationError, JSONDecodeError, ValueError, TypeError) as exc:
            raise ContractMismatchError() from exc

    @staticmethod
    def _parse_grid(response: httpx.Response) -> WikiGrid:
        try:
            return map_grid(WikiGridWire.model_validate(response.json()))
        except (ValidationError, JSONDecodeError, ValueError, TypeError) as exc:
            raise ContractMismatchError() from exc

    async def _resolve_page_id(
        self,
        locator: PageLocator,
        credentials: RequestCredentials | None,
    ) -> int:
        if locator.page_id is not None:
            return locator.page_id
        return (await self.get_page(locator, credentials=credentials)).id

    @staticmethod
    def _page_collection_params(page_input: PageListInput) -> dict[str, str | int]:
        params: dict[str, str | int] = {"page_size": page_input.page_size}
        if page_input.cursor:
            params["cursor"] = page_input.cursor
        return params

    async def _page_collection_request(
        self,
        path: str,
        page_input: PageListInput,
        *,
        credentials: RequestCredentials | None,
    ) -> httpx.Response:
        return await self._request(
            "GET",
            path,
            semantics=RequestSemantics.SAFE_READ,
            credentials=credentials,
            params=self._page_collection_params(page_input),
        )

    async def get_tree(self, slug: str) -> dict[str, Any]:
        result = await self.get_descendants(DescendantsInput(locator=PageLocator(slug=slug)))
        return result.model_dump(mode="json")

    @staticmethod
    def _slug_from_url(url: str) -> str:
        parsed = httpx.URL(url)
        if parsed.scheme != "https" or parsed.host not in {"wiki.yandex.ru", "wiki.yandex.com"}:
            raise ValueError("invalid Wiki page URL")
        slug = parsed.path.strip("/")
        if not slug:
            raise ValueError("invalid Wiki page URL")
        return slug

import asyncio
import secrets
from itertools import zip_longest
from typing import Any, Literal

import structlog

from ..models.common import FetchResult, ResourceRef, SearchResult, SourceStatus
from ..models.disk import DiskResource, DiskSearchResponse
from ..models.errors import UpstreamUnavailable, YandexWorkspaceError
from ..models.wiki import WikiPage, WikiSearchItem, WikiSearchResponse
from ..policies.cursors import (
    CursorCodec,
    DiskOffsetState,
    WorkspaceCursorSources,
    WorkspaceCursorV1,
)
from .disk import DiskService
from .wiki import WikiService

logger = structlog.get_logger()


class WorkspaceService:
    def __init__(
        self,
        disk: DiskService | None,
        wiki: WikiService | None,
        *,
        cursor_codec: CursorCodec | None = None,
    ) -> None:
        self.disk = disk
        self.wiki = wiki
        self.cursor_codec = cursor_codec or CursorCodec((secrets.token_bytes(32),))

    async def search(
        self,
        query: str,
        limit: int = 20,
        cursor: str | None = None,
        *,
        principal: str = "trusted-local",
    ) -> SearchResult:
        logger.info("workspace.search", query_length=len(query))
        enabled: list[Literal["wiki", "disk"]] = []
        if self.wiki and self.wiki.can_read:
            enabled.append("wiki")
        if self.disk and self.disk.can_read:
            enabled.append("disk")

        disk_offset = 0
        seen: list[str] = []
        wiki_roots = set(self.wiki.allowed_roots) if "wiki" in enabled and self.wiki else set()
        if cursor:
            state = self.cursor_codec.decode_workspace(
                cursor,
                query=query,
                principal=principal,
                enabled_sources=set(enabled),
                allowed_roots=wiki_roots,
            )
            seen = list(state.seen)
            if state.sources.disk:
                disk_offset = state.sources.disk.offset

        source_names: list[str] = []
        calls: list[Any] = []
        if "wiki" in enabled and self.wiki:
            source_names.append("wiki")
            calls.append(self.wiki.search(query, limit=limit))
        if "disk" in enabled and self.disk:
            source_names.append("disk")
            calls.append(
                self.disk.search(
                    query,
                    limit=limit,
                    offset=disk_offset,
                    principal=principal,
                )
            )

        outcomes = await asyncio.gather(*calls, return_exceptions=True) if calls else []
        wiki_response: WikiSearchResponse | None = None
        disk_response: DiskSearchResponse | None = None
        partial_failures: dict[str, str] = {}
        sources: dict[str, SourceStatus] = {}
        failure_count = 0
        for source, outcome in zip(source_names, outcomes, strict=True):
            if isinstance(outcome, asyncio.CancelledError):
                raise outcome
            if isinstance(outcome, BaseException):
                failure_count += 1
                category = (
                    outcome.category
                    if isinstance(outcome, YandexWorkspaceError)
                    else "upstream_error"
                )
                partial_failures[source] = category
                sources[source] = SourceStatus(state="failure", error_category=category)
                continue
            if source == "wiki":
                wiki_response = outcome
                sources[source] = SourceStatus(
                    state="degraded" if outcome.degraded else "success",
                    search_mode=outcome.search_mode,
                )
            else:
                disk_response = outcome
                sources[source] = SourceStatus(state="success")

        if source_names and failure_count == len(source_names):
            raise UpstreamUnavailable()

        wiki_refs = self._wiki_refs(wiki_response.results if wiki_response else [])
        disk_refs = self._disk_refs(disk_response.items if disk_response else [])
        seen_set = set(seen)
        results: list[ResourceRef] = []
        for wiki_ref, disk_ref in zip_longest(wiki_refs, disk_refs):
            for resource in (wiki_ref, disk_ref):
                if resource is None:
                    continue
                identity_hash = self.cursor_codec.item_hash(resource.source, resource.id)
                if identity_hash in seen_set:
                    continue
                seen_set.add(identity_hash)
                seen.append(identity_hash)
                results.append(resource)
                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break

        next_disk_offset: int | None = None
        if disk_response and disk_response.next_cursor and self.disk:
            disk_state = self.disk.cursor_codec.decode_disk(
                disk_response.next_cursor,
                query=query,
                principal=principal,
            )
            next_disk_offset = disk_state.offset

        next_cursor = None
        if next_disk_offset is not None:
            next_cursor = self.cursor_codec.encode_workspace(
                WorkspaceCursorV1(
                    query_hash=self.cursor_codec.query_hash(query),
                    principal_hash=self.cursor_codec.principal_hash(principal),
                    sources=WorkspaceCursorSources(
                        enabled=enabled,
                        root_hashes=[
                            self.cursor_codec.root_hash(root) for root in sorted(wiki_roots)
                        ],
                        disk=DiskOffsetState(offset=next_disk_offset),
                    ),
                    seen=seen[-100:],
                )
            )
        return SearchResult(
            results=results,
            next_cursor=next_cursor,
            partial_failures=partial_failures,
            sources=sources,
        )

    @staticmethod
    def _wiki_refs(items: list[WikiSearchItem]) -> list[ResourceRef]:
        return [
            ResourceRef(
                id=f"wiki:page:{item.slug}",
                source="wiki",
                title=item.title or item.slug or "",
                url=item.url,
                type=item.type,
                modified_at=item.modified_at,
                locator=item.slug,
            )
            for item in items
            if item.slug
        ]

    @staticmethod
    def _disk_refs(items: list[DiskResource]) -> list[ResourceRef]:
        return [
            ResourceRef(
                id=f"disk:path:{item.path}",
                source="disk",
                title=item.name,
                url=item.public_url,
                type=item.type,
                modified_at=item.modified_at,
                locator=item.path,
            )
            for item in items
            if item.path
        ]

    async def fetch(self, resource_id: str) -> FetchResult:
        logger.info("workspace.fetch", resource_id=resource_id)
        if resource_id.startswith("wiki:page:"):
            if not self.wiki or not self.wiki.can_read:
                raise ValueError("Wiki is not enabled or readable")
            slug = resource_id.replace("wiki:page:", "", 1)
            page = await self.wiki.get_page(slug)
            if isinstance(page, WikiPage):
                title, content, url = page.title or "", page.content or "", page.url
            else:  # compatibility for injected legacy client doubles
                title = page.get("title", "")
                content = page.get("content", "")
                url = page.get("url")
            return FetchResult(
                id=resource_id,
                title=title,
                text=content,
                url=url,
                metadata={"source": "wiki"},
            )
        if resource_id.startswith("disk:path:"):
            if not self.disk or not self.disk.can_read:
                raise ValueError("Disk is not enabled or readable")
            path = resource_id.replace("disk:path:", "", 1)
            meta = await self.disk.get_metadata(path)
            if isinstance(meta, DiskResource):
                mime = meta.mime_type or ""
                title = meta.name
                public_url = meta.public_url
                size = meta.size
            else:  # compatibility for injected legacy service doubles
                mime = meta.get("mime_type", "")
                title = meta.get("name", "")
                public_url = meta.get("public_url")
                size = meta.get("size")
            text = None
            if mime.startswith("text/") or mime == "application/json":
                text = await self.disk.read_file(path)
            return FetchResult(
                id=resource_id,
                title=title,
                text=text,
                url=public_url,
                metadata={"source": "disk", "mime_type": mime, "size": size},
            )
        raise ValueError(f"Unknown resource ID format: {resource_id}")

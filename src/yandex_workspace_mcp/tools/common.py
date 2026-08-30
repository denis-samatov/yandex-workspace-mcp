from typing import Annotated, Protocol

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from ..auth.scopes import OperationClass, WorkspacePrincipal, WorkspaceScope, require_scope
from ..models.common import FetchResult, SearchResult
from ..services.workspace import WorkspaceService


class CommonApplication(Protocol):
    @property
    def principal(self) -> WorkspacePrincipal: ...

    def require_workspace_service(self) -> WorkspaceService: ...


def register_common_tools(mcp: MCPServer, application: CommonApplication) -> None:
    @mcp.tool(
        name="search",
        description="Search across Yandex Disk and Yandex Wiki",
        annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True),
        meta={"required_scopes": [WorkspaceScope.READ.value]},
    )
    async def search(
        query: str,
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
        cursor: str | None = None,
    ) -> SearchResult:
        require_scope(application.principal, OperationClass.READ)
        return await application.require_workspace_service().search(
            query,
            limit,
            cursor,
            principal=application.principal.principal_id,
        )

    @mcp.tool(
        name="fetch",
        description="Fetch a canonical resource by ID from Yandex Workspace",
        annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True),
        meta={"required_scopes": [WorkspaceScope.READ.value]},
    )
    async def fetch(resource_id: str) -> FetchResult:
        require_scope(application.principal, OperationClass.READ)
        return await application.require_workspace_service().fetch(resource_id)

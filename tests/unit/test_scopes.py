import pytest

from yandex_workspace_mcp.auth.scopes import (
    OperationClass,
    WorkspacePrincipal,
    WorkspaceScope,
    effective_static_scopes,
    require_scope,
    scopes_for_permissions,
)
from yandex_workspace_mcp.models.errors import PermissionDenied


def test_scope_hierarchy_is_monotonic() -> None:
    assert scopes_for_permissions(can_read=False, can_write=False, can_delete=True) == frozenset(
        {WorkspaceScope.READ, WorkspaceScope.WRITE, WorkspaceScope.DELETE}
    )
    assert scopes_for_permissions(can_read=False, can_write=True, can_delete=False) == frozenset(
        {WorkspaceScope.READ, WorkspaceScope.WRITE}
    )


def test_static_scopes_are_limited_by_permission_ceiling() -> None:
    scopes = effective_static_scopes(
        ["workspace:delete"],
        scopes_for_permissions(can_read=True, can_write=True, can_delete=False),
    )
    assert scopes == frozenset({WorkspaceScope.READ, WorkspaceScope.WRITE})


def test_each_operation_requires_its_effective_scope() -> None:
    principal = WorkspacePrincipal("reader", frozenset({WorkspaceScope.READ}))
    require_scope(principal, OperationClass.READ)
    with pytest.raises(PermissionDenied):
        require_scope(principal, OperationClass.WRITE)
    with pytest.raises(PermissionDenied):
        require_scope(principal, OperationClass.DELETE)

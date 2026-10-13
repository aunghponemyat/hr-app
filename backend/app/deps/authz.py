from collections.abc import Callable
from typing import Annotated, cast

from fastapi import Depends, Request

from app.core.errors import AppError
from app.deps.auth import CurrentEmployee, DatabaseSession, require_password_changed
from app.services.authorization_service import (
    AuthorizationContext,
    PermissionGrant,
    Scope,
    authorize,
    has_permission,
    is_admin,
    load_permissions,
    manages_team_of,
    resolve_target_employee,
    scoped_employee_ids_query,
    scopes_for,
)

__all__ = [
    "AuthorizationContext",
    "CurrentCaller",
    "Scope",
    "authorize",
    "get_authorization_context",
    "has_permission",
    "is_admin",
    "manages_team_of",
    "require_permission",
    "resolve_target_employee",
    "scoped_employee_ids_query",
    "scopes_for",
]


def get_authorization_context(
    request: Request, employee: CurrentEmployee, session: DatabaseSession
) -> AuthorizationContext:
    cache = cast(
        dict[int, frozenset[PermissionGrant]] | None,
        getattr(request.state, "permission_cache", None),
    )
    if cache is None:
        cache = {}
        request.state.permission_cache = cache
    if employee.role_id not in cache:
        cache[employee.role_id] = load_permissions(session, employee.role_id)
    return AuthorizationContext(employee, session, cache[employee.role_id])


CurrentCaller = Annotated[AuthorizationContext, Depends(get_authorization_context)]


def require_permission(
    resource: str,
    action: str,
    *,
    allowed_scopes: frozenset[Scope] | None = None,
    allow_password_change_required: bool = False,
) -> Callable[[AuthorizationContext], AuthorizationContext]:
    """Authenticate, enforce the password gate, and require a resource/action scope.

    Specific targets still require authorize()/resolve_target_employee(); list queries
    must use scoped_employee_ids_query(). Only GET /me opts out of the password gate.
    """

    def check_permission(caller: CurrentCaller) -> AuthorizationContext:
        if not allow_password_change_required:
            require_password_changed(caller.employee)
        scopes = has_permission(caller, resource, action)
        if not scopes or (allowed_scopes is not None and not scopes.intersection(allowed_scopes)):
            raise AppError(403, "PERMISSION_DENIED", "Permission denied.")
        return caller

    return check_permission

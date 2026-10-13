from dataclasses import dataclass, field
from typing import Literal, cast

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.errors import AppError
from app.models import Employee, Permission, RolePermission, TeamManager

Scope = Literal["self", "team", "any"]


@dataclass(frozen=True)
class PermissionGrant:
    code: str
    resource: str
    action: str
    scope: Scope


@dataclass(frozen=True)
class AuthorizationContext:
    employee: Employee = field(repr=False)
    session: Session = field(repr=False)
    permissions: frozenset[PermissionGrant]


def load_permissions(session: Session, role_id: int) -> frozenset[PermissionGrant]:
    permissions = session.scalars(
        select(Permission)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == role_id)
        .execution_options(populate_existing=True)
    )
    return frozenset(
        PermissionGrant(
            permission.code, permission.resource, permission.action, cast(Scope, permission.scope)
        )
        for permission in permissions
        if permission.scope in {"self", "team", "any"}
        and permission.code == f"{permission.resource}.{permission.action}.{permission.scope}"
    )


def has_permission(caller: AuthorizationContext, resource: str, action: str) -> set[Scope]:
    """Return the scopes granted for this exact resource/action pair."""
    return {
        permission.scope
        for permission in caller.permissions
        if permission.code == f"{resource}.{action}.{permission.scope}"
    }


def scopes_for(caller: AuthorizationContext, resource: str, action: str) -> set[Scope]:
    return has_permission(caller, resource, action)


def managed_team_ids_query(caller: AuthorizationContext) -> Select[tuple[int]]:
    return select(TeamManager.team_id).where(
        TeamManager.employee_id == caller.employee.id,
        TeamManager.removed_at.is_(None),
    )


def manages_team_of(caller: AuthorizationContext, target: Employee) -> bool:
    if target.team_id is None:
        return False
    return bool(
        caller.session.scalar(
            select(
                managed_team_ids_query(caller)
                .where(
                    TeamManager.team_id == target.team_id,
                )
                .exists()
            )
        )
    )


def authorize(
    caller: AuthorizationContext,
    resource: str,
    action: str,
    target_employee: Employee | None = None,
) -> None:
    scopes = has_permission(caller, resource, action)
    if not scopes:
        raise AppError(403, "PERMISSION_DENIED", "Permission denied.")
    if "any" in scopes:
        return
    if target_employee is None:
        if "self" in scopes:
            return
        raise AppError(403, "PERMISSION_DENIED", "A scoped target is required.")
    if "self" in scopes and caller.employee.id == target_employee.id:
        return
    if "team" in scopes and manages_team_of(caller, target_employee):
        return
    raise AppError(403, "OUT_OF_SCOPE", "Employee is outside your permitted scope.")


def scoped_employee_ids_query(
    caller: AuthorizationContext, resource: str, action: str
) -> Select[tuple[int]]:
    scopes = has_permission(caller, resource, action)
    if not scopes:
        raise AppError(403, "PERMISSION_DENIED", "Permission denied.")
    query = select(Employee.id)
    if "any" in scopes:
        return query
    if "team" in scopes:
        return query.where(
            or_(
                Employee.id == caller.employee.id,
                Employee.team_id.in_(managed_team_ids_query(caller)),
            )
        )
    return query.where(Employee.id == caller.employee.id)


def resolve_target_employee(
    caller: AuthorizationContext, resource: str, action: str, employee_id: int
) -> Employee:
    """Check permission/scope before exposing whether a specific employee exists."""
    scopes = has_permission(caller, resource, action)
    if not scopes:
        raise AppError(403, "PERMISSION_DENIED", "Permission denied.")
    if not scopes.intersection({"team", "any"}) and employee_id != caller.employee.id:
        raise AppError(403, "OUT_OF_SCOPE", "Employee is outside your permitted scope.")
    target = caller.session.execute(
        select(Employee)
        .where(Employee.id == employee_id)
        .options(joinedload(Employee.team))
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if target is None:
        if scopes.intersection({"team", "any"}):
            raise AppError(404, "NOT_FOUND", "Employee not found.")
        raise AppError(403, "OUT_OF_SCOPE", "Employee is outside your permitted scope.")
    authorize(caller, resource, action, target)
    return target


def is_admin(caller: AuthorizationContext) -> bool:
    return "any" in has_permission(caller, "employee", "create")

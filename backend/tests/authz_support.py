from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.deps.authz import (
    AuthorizationContext,
    get_authorization_context,
    require_permission,
    resolve_target_employee,
    scoped_employee_ids_query,
)
from app.models import Employee, Role, Team, TeamManager, TeamMember
from app.schemas.common import RequestSchema
from app.utils.time import utc_now


@dataclass
class AuthzScenario:
    employees: dict[str, Employee]
    teams: dict[str, Team]
    managers: dict[str, TeamManager]

    def ids(self) -> set[int]:
        return {employee.id for employee in self.employees.values()}

    def team_ids(self, team: str) -> set[int]:
        return {
            employee.id
            for employee in self.employees.values()
            if employee.team_id == self.teams[team].id
        }


def create_employee(
    session: Session, key: str, role: str, password_hash: str, team: Team | None = None
) -> Employee:
    role_id = session.execute(select(Role.id).where(Role.name == role)).scalar_one()
    employee = Employee(
        employee_id=key.upper(),
        role_id=role_id,
        password_hash=password_hash,
        first_name=key,
        last_name="Fixture",
        team=team,
        must_change_password=False,
    )
    session.add(employee)
    session.flush()
    if team is not None:
        session.add(TeamMember(team_id=team.id, employee_id=employee.id))
        session.flush()
    return employee


def create_scenario(session: Session, password: str) -> AuthzScenario:
    teams = {key: Team(name=f"Authz team {key}") for key in ("a", "b")}
    session.add_all(teams.values())
    session.flush()
    stored_hash = hash_password(password)
    employees = {
        "employee_a": create_employee(session, "employee_a", "employee", stored_hash, teams["a"]),
        "employee_b": create_employee(session, "employee_b", "employee", stored_hash, teams["b"]),
        "senior": create_employee(session, "senior", "senior_staff", stored_hash, teams["a"]),
        "manager_a": create_employee(
            session, "manager_a", "reporting_manager", stored_hash, teams["a"]
        ),
        "manager_b": create_employee(
            session, "manager_b", "reporting_manager", stored_hash, teams["b"]
        ),
        "hr": create_employee(session, "hr", "hr", stored_hash),
        "c_level": create_employee(session, "c_level", "c_level", stored_hash),
        "unassigned": create_employee(session, "unassigned", "employee", stored_hash),
    }
    managers = {
        key: TeamManager(
            team_id=teams[key].id,
            employee_id=employees[f"manager_{key}"].id,
            assigned_at=utc_now() - timedelta(days=1),
        )
        for key in teams
    }
    session.add_all(managers.values())
    session.flush()
    return AuthzScenario(employees, teams, managers)


class TargetRequest(RequestSchema):
    employee_id: int = Field(gt=0, le=2**64 - 1)


class PageRequest(RequestSchema):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=25, ge=1, le=100)


class TargetResponse(BaseModel):
    employee_id: int


class IdListResponse(BaseModel):
    ids: list[int]
    total: int
    page: int
    page_size: int


class PermissionProbeResponse(BaseModel):
    allowed: bool


class CacheProbeResponse(BaseModel):
    same_context: bool
    same_permissions: bool


AttendanceReader = Annotated[
    AuthorizationContext, Depends(require_permission("attendance", "read"))
]
AttendanceEditor = Annotated[
    AuthorizationContext, Depends(require_permission("attendance", "update"))
]
LeaveReader = Annotated[AuthorizationContext, Depends(require_permission("leave", "read"))]
MemberReader = Annotated[
    AuthorizationContext,
    Depends(
        require_permission(
            "employee",
            "read",
            allowed_scopes=frozenset({"team", "any"}),
        )
    ),
]
AdminCreator = Annotated[
    AuthorizationContext,
    Depends(
        require_permission(
            "employee",
            "create",
            allowed_scopes=frozenset({"any"}),
        )
    ),
]


def scoped_list(caller: AuthorizationContext, resource: str, page: PageRequest) -> IdListResponse:
    query = scoped_employee_ids_query(caller, resource, "read")
    total = int(caller.session.scalar(select(func.count()).select_from(query.subquery())) or 0)
    ids = list(
        caller.session.scalars(
            query.order_by(Employee.id)
            .limit(page.page_size)
            .offset((page.page - 1) * page.page_size)
        )
    )
    return IdListResponse(ids=ids, total=total, page=page.page, page_size=page.page_size)


def install_authz_probes(app: FastAPI) -> None:
    """These routes test authorization only and are never installed on the production app."""
    router = APIRouter(prefix="/api/v1")

    @router.get("/team/members", response_model=IdListResponse)
    def members(caller: MemberReader, page: Annotated[PageRequest, Query()]) -> IdListResponse:
        return scoped_list(caller, "employee", page)

    @router.get("/authz/attendance", response_model=IdListResponse)
    def attendance_list(
        caller: AttendanceReader, page: Annotated[PageRequest, Query()]
    ) -> IdListResponse:
        return scoped_list(caller, "attendance", page)

    @router.get("/authz/leave", response_model=IdListResponse)
    def leave_list(caller: LeaveReader, page: Annotated[PageRequest, Query()]) -> IdListResponse:
        return scoped_list(caller, "leave", page)

    @router.get("/authz/attendance/target", response_model=TargetResponse)
    def attendance_target(
        caller: AttendanceReader, target: Annotated[TargetRequest, Query()]
    ) -> TargetResponse:
        employee = resolve_target_employee(caller, "attendance", "read", target.employee_id)
        return TargetResponse(employee_id=employee.id)

    @router.post("/authz/attendance/edit", response_model=TargetResponse)
    def attendance_edit(target: TargetRequest, caller: AttendanceEditor) -> TargetResponse:
        employee = resolve_target_employee(caller, "attendance", "update", target.employee_id)
        return TargetResponse(employee_id=employee.id)

    @router.get("/authz/admin-create", response_model=PermissionProbeResponse)
    def admin_create(_caller: AdminCreator) -> PermissionProbeResponse:
        return PermissionProbeResponse(allowed=True)

    @router.get("/authz/cache", response_model=CacheProbeResponse)
    def cache(
        request: Request, attendance: AttendanceReader, leave: LeaveReader
    ) -> CacheProbeResponse:
        reloaded = get_authorization_context(request, attendance.employee, attendance.session)
        return CacheProbeResponse(
            same_context=attendance is leave,
            same_permissions=attendance.permissions is reloaded.permissions,
        )

    app.include_router(router)

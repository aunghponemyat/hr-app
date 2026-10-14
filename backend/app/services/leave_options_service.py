from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings
from app.models import Employee, LeaveReason, LeaveType, Permission, RolePermission, TeamManager
from app.schemas.leave import LeaveChoice, LeaveOptions, LeaveReasonChoice
from app.services.attendance_presenter import employee_identity
from app.services.authorization_service import AuthorizationContext, authorize
from app.utils.time import utc_now


def eligible_role_ids(session: Session, codes: set[str]) -> set[int]:
    rows = session.execute(
        select(RolePermission.role_id, Permission)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(Permission.code.in_(codes))
    )
    return {
        role_id
        for role_id, permission in rows
        if permission.code in codes
        and permission.code == f"{permission.resource}.{permission.action}.{permission.scope}"
        and permission.scope in {"team", "any"}
    }


def eligible_managers(session: Session, employee: Employee) -> list[Employee]:
    base = select(Employee).where(Employee.is_active.is_(True), Employee.id != employee.id)
    managers: list[Employee] = []
    if employee.team_id is not None:
        team_ids = select(TeamManager.employee_id).where(
            TeamManager.team_id == employee.team_id, TeamManager.removed_at.is_(None)
        )
        managers = list(
            session.scalars(
                base.where(
                    Employee.id.in_(team_ids),
                    Employee.role_id.in_(
                        eligible_role_ids(session, {"leave.decide.team", "leave.decide.any"})
                    ),
                )
                .options(joinedload(Employee.team))
                .order_by(Employee.id)
                .execution_options(populate_existing=True)
            )
        )
    if not managers:
        managers = list(
            session.scalars(
                base.where(Employee.role_id.in_(eligible_role_ids(session, {"leave.decide.any"})))
                .options(joinedload(Employee.team))
                .order_by(Employee.id)
                .execution_options(populate_existing=True)
            )
        )
    return managers


def options(caller: AuthorizationContext, settings: Settings) -> LeaveOptions:
    authorize(caller, "leave", "create", caller.employee)
    return LeaveOptions(
        types=[
            LeaveChoice.model_validate(item)
            for item in caller.session.scalars(
                select(LeaveType).where(LeaveType.is_active.is_(True)).order_by(LeaveType.id)
            )
        ],
        reasons=[
            LeaveReasonChoice.model_validate(item)
            for item in caller.session.scalars(
                select(LeaveReason).where(LeaveReason.is_active.is_(True)).order_by(LeaveReason.id)
            )
        ],
        managers=[
            employee_identity(employee)
            for employee in eligible_managers(caller.session, caller.employee)
        ],
        today=utc_now().astimezone(ZoneInfo(settings.app_timezone)).date(),
        working_weekdays=sorted(settings.working_weekday_numbers),
        max_days_per_request=settings.leave_max_days_per_request,
        backdate_days=settings.leave_backdate_days,
    )

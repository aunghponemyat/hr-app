from datetime import datetime

from sqlalchemy import select, update

from app.core.errors import AppError
from app.models import Employee, Team, TeamManager, TeamMember
from app.services.admin_support import audit, get_entity
from app.services.authorization_service import AuthorizationContext, load_permissions
from app.utils.time import utc_now


def manager_eligible(caller: AuthorizationContext, employee: Employee) -> bool:
    return employee.is_active and any(
        grant.code in {"attendance.read.team", "attendance.read.any"}
        for grant in load_permissions(caller.session, employee.role_id)
    )


def move_employee(
    caller: AuthorizationContext,
    employee: Employee,
    team_id: int | None,
    *,
    now: datetime | None = None,
) -> None:
    """Caller owns the administrative serialization lock and employee lock."""
    session = caller.session
    if team_id is not None:
        get_entity(session, Team, team_id, lock=True)
    if employee.team_id == team_id:
        return
    instant = now or utc_now()
    before_team_id = employee.team_id
    session.execute(
        update(TeamMember)
        .where(
            TeamMember.employee_id == employee.id,
            TeamMember.left_at.is_(None),
        )
        .values(left_at=instant)
    )
    employee.team_id = team_id
    if team_id is not None:
        # Microseconds distinguish repeated moves back into a team.
        session.add(TeamMember(team_id=team_id, employee_id=employee.id, joined_at=instant))
    session.flush()
    session.expire(employee, ["team"])
    audit(
        caller,
        "employee.team_change",
        "employee",
        employee.id,
        {"team_id": before_team_id},
        {"team_id": team_id},
    )


def close_manager_assignments(caller: AuthorizationContext, employee: Employee) -> None:
    if manager_eligible(caller, employee):
        return
    now = utc_now()
    assignments = caller.session.scalars(
        select(TeamManager)
        .where(
            TeamManager.employee_id == employee.id,
            TeamManager.removed_at.is_(None),
        )
        .with_for_update()
    ).all()
    for assignment in assignments:
        assignment.removed_at = now
        audit(
            caller,
            "team.manager_remove",
            "team",
            assignment.team_id,
            {"employee_id": employee.id},
            {"removed_at": now.isoformat()},
        )


def validate_assignee(employee: Employee) -> None:
    if not employee.is_active:
        raise AppError(422, "INACTIVE_EMPLOYEE", "Only active employees can be assigned.")

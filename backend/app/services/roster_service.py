from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.core.config import Settings
from app.core.errors import AppError
from app.models import Attendance, Employee
from app.schemas.admin import PageQuery, PageResponse, TeamMemberResponse
from app.services.admin_support import employee_response, page_rows
from app.services.authorization_service import (
    AuthorizationContext,
    has_permission,
    scoped_employee_ids_query,
)
from app.utils.time import utc_now


def list_team_members(
    caller: AuthorizationContext, query: PageQuery, settings: Settings
) -> PageResponse[TeamMemberResponse]:
    if not has_permission(caller, "employee", "read").intersection({"team", "any"}):
        raise AppError(403, "PERMISSION_DENIED", "Permission denied.")
    rows, total = page_rows(
        caller.session,
        select(Employee)
        .where(Employee.id.in_(scoped_employee_ids_query(caller, "employee", "read")))
        .options(joinedload(Employee.role), joinedload(Employee.team))
        .order_by(Employee.id),
        query,
    )
    today = utc_now().astimezone(ZoneInfo(settings.app_timezone)).date()
    statuses = {
        employee_id: status
        for employee_id, status in caller.session.execute(
            select(Attendance.employee_id, Attendance.status).where(
                Attendance.employee_id.in_([row.id for row in rows]),
                Attendance.attendance_date == today,
            )
        ).all()
    }
    fallback = None if today.weekday() in settings.working_weekday_numbers else "weekend"
    return PageResponse(
        items=[
            TeamMemberResponse(
                **employee_response(row, settings).model_dump(),
                today_status=statuses[row.id].value if row.id in statuses else fallback,
            )
            for row in rows
        ],
        total=total,
        page=query.page,
        page_size=query.page_size,
    )

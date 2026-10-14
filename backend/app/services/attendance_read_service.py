from datetime import date, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings
from app.core.errors import AppError
from app.models import Attendance, Employee
from app.schemas.attendance import (
    AttendanceQuery,
    AttendanceTableResponse,
    AttendanceTableRow,
    CalendarEntry,
    CalendarQuery,
    CalendarResponse,
    DateRange,
    LeaveInfo,
    TeamAttendanceQuery,
    TeamAttendanceResponse,
    TeamAttendanceRow,
)
from app.services.admin_support import page_rows
from app.services.attendance_presenter import calendar_entry, employee_identity, summarize
from app.services.authorization_service import (
    AuthorizationContext,
    has_permission,
    resolve_target_employee,
    scoped_employee_ids_query,
)
from app.services.leave_calendar_service import approved_leave_days, leave_years
from app.services.period_service import history_start, resolve_period
from app.utils.time import utc_now


def attendance_rows(
    session: Session, employee_ids: list[int], period: DateRange
) -> dict[tuple[int, date], Attendance]:
    if not employee_ids:
        return {}
    rows = session.scalars(
        select(Attendance)
        .where(
            Attendance.employee_id.in_(employee_ids),
            Attendance.attendance_date.between(period.from_date, period.to_date),
        )
        .options(joinedload(Attendance.work_location))
        .execution_options(populate_existing=True)
    )
    return {(row.employee_id, row.attendance_date): row for row in rows}


def entries_for(
    employee_id: int,
    rows: dict[tuple[int, date], Attendance],
    period: DateRange,
    today: date,
    settings: Settings,
    leaves: dict[tuple[int, date], list[LeaveInfo]] | None = None,
) -> list[CalendarEntry]:
    return [
        calendar_entry(
            day,
            rows.get((employee_id, day)),
            today,
            settings,
            (leaves or {}).get((employee_id, day), []),
        )
        for day in (
            period.from_date + timedelta(days=index)
            for index in range((period.to_date - period.from_date).days + 1)
        )
    ]


def available_years(caller: AuthorizationContext, employee_id: int, today: date) -> list[int]:
    query = select(func.year(Attendance.attendance_date)).where(
        Attendance.employee_id == employee_id
    )
    if "any" not in has_permission(caller, "attendance", "read"):
        query = query.where(Attendance.attendance_date >= history_start(today))
    years = [
        int(year)
        for year in caller.session.scalars(
            query.distinct().order_by(func.year(Attendance.attendance_date).desc())
        )
    ]
    leave_data_years = leave_years(
        caller.session,
        employee_id,
        None if "any" in has_permission(caller, "attendance", "read") else history_start(today),
    )
    return sorted(set(years) | leave_data_years, reverse=True) or [today.year]


def calendar(
    caller: AuthorizationContext, query: CalendarQuery, settings: Settings
) -> CalendarResponse:
    employee = resolve_target_employee(
        caller, "attendance", "read", query.employee_id or caller.employee.id
    )
    today = utc_now().astimezone(ZoneInfo(settings.app_timezone)).date()
    period = resolve_period(
        query, today, settings, unrestricted="any" in has_permission(caller, "attendance", "read")
    )
    rows = attendance_rows(caller.session, [employee.id], period)
    leaves = approved_leave_days(caller.session, [employee.id], period, settings)
    entries = entries_for(employee.id, rows, period, today, settings, leaves)
    return CalendarResponse(
        employee=employee_identity(employee),
        period=period,
        entries=entries,
        summary=summarize(entries),
        available_years=available_years(caller, employee.id, today),
    )


def table(
    caller: AuthorizationContext, query: AttendanceQuery, settings: Settings
) -> AttendanceTableResponse:
    scope = scoped_employee_ids_query(caller, "attendance", "read")
    employees = select(Employee).where(Employee.id.in_(scope))
    if query.employee_id is not None:
        resolve_target_employee(caller, "attendance", "read", query.employee_id)
        employees = employees.where(Employee.id == query.employee_id)
    today = utc_now().astimezone(ZoneInfo(settings.app_timezone)).date()
    period = resolve_period(
        query, today, settings, unrestricted="any" in has_permission(caller, "attendance", "read")
    )
    count = caller.session.scalar(select(func.count()).select_from(employees.subquery())) or 0
    days = (period.to_date - period.from_date).days + 1
    total = count * days
    offset = (query.page - 1) * query.page_size
    items: list[AttendanceTableRow] = []
    if offset < total:
        first_day = offset % days
        needed_employees = (first_day + query.page_size + days - 1) // days
        selected = list(
            caller.session.scalars(
                employees.options(joinedload(Employee.team))
                .order_by(Employee.id)
                .offset(offset // days)
                .limit(needed_employees)
            )
        )
        rows = attendance_rows(caller.session, [employee.id for employee in selected], period)
        leaves = approved_leave_days(
            caller.session, [employee.id for employee in selected], period, settings
        )
        for employee in selected:
            for day_index in range(first_day, days):
                day = period.from_date + timedelta(days=day_index)
                entry = calendar_entry(
                    day,
                    rows.get((employee.id, day)),
                    today,
                    settings,
                    leaves.get((employee.id, day), []),
                )
                items.append(
                    AttendanceTableRow(**entry.model_dump(), employee=employee_identity(employee))
                )
                if len(items) == query.page_size:
                    break
            first_day = 0
            if len(items) == query.page_size:
                break
    return AttendanceTableResponse(
        items=items, total=total, page=query.page, page_size=query.page_size, period=period
    )


def team_summary(
    caller: AuthorizationContext, query: TeamAttendanceQuery, settings: Settings
) -> TeamAttendanceResponse:
    if not has_permission(caller, "attendance", "read").intersection({"team", "any"}):
        raise AppError(403, "PERMISSION_DENIED", "Permission denied.")
    today = utc_now().astimezone(ZoneInfo(settings.app_timezone)).date()
    period = resolve_period(
        query, today, settings, unrestricted="any" in has_permission(caller, "attendance", "read")
    )
    employees, count = page_rows(
        caller.session,
        select(Employee)
        .where(Employee.id.in_(scoped_employee_ids_query(caller, "attendance", "read")))
        .options(joinedload(Employee.team))
        .order_by(Employee.id),
        query,
    )
    rows = attendance_rows(caller.session, [employee.id for employee in employees], period)
    leaves = approved_leave_days(
        caller.session, [employee.id for employee in employees], period, settings
    )
    return TeamAttendanceResponse(
        items=[
            TeamAttendanceRow(
                employee=employee_identity(employee),
                summary=summarize(entries_for(employee.id, rows, period, today, settings, leaves)),
            )
            for employee in employees
        ],
        total=count,
        page=query.page,
        page_size=query.page_size,
        period=period,
    )

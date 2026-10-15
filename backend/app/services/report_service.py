from collections.abc import Iterator
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import Select, select
from sqlalchemy.orm import joinedload

from app.core.config import Settings
from app.core.errors import AppError
from app.models import Employee, LeaveRequest, Team
from app.models.enums import LeaveDuration
from app.schemas.attendance import DateRange, PeriodQuery
from app.schemas.report import AdminExportQuery, AttendanceCsvRow, LeaveCsvRow, SelfExportQuery
from app.services.admin_support import get_entity
from app.services.attendance_presenter import calendar_entry, employee_identity, worked_hours
from app.services.attendance_read_service import attendance_rows
from app.services.authorization_service import (
    AuthorizationContext,
    has_permission,
    resolve_target_employee,
    scoped_employee_ids_query,
)
from app.services.csv_service import CsvExport, csv_chunks, export_filename
from app.services.leave_calendar_service import approved_leave_days
from app.services.leave_service import requests_query
from app.services.period_service import resolve_period
from app.utils.time import utc_now

EMPLOYEE_BATCH_SIZE = 25
LEAVE_BATCH_SIZE = 100


def export_period(
    caller: AuthorizationContext,
    query: SelfExportQuery | AdminExportQuery,
    settings: Settings,
    today: date,
) -> DateRange:
    values = {"from": query.from_date, "to": query.to_date} if query.from_date is not None else {}
    return resolve_period(
        PeriodQuery.model_validate(values),
        today,
        settings,
        unrestricted="any" in has_permission(caller, "report", "export"),
    )


def admin_employees(
    caller: AuthorizationContext, query: AdminExportQuery
) -> Select[tuple[Employee]]:
    if "any" not in has_permission(caller, "report", "export"):
        raise AppError(403, "PERMISSION_DENIED", "Permission denied.")
    statement = select(Employee).where(
        Employee.id.in_(scoped_employee_ids_query(caller, "report", "export"))
    )
    if query.employee_id is not None:
        resolve_target_employee(caller, "report", "export", query.employee_id)
        statement = statement.where(Employee.id == query.employee_id)
    if query.team_id is not None:
        get_entity(caller.session, Team, query.team_id)
        statement = statement.where(Employee.team_id == query.team_id)
    return statement


def attendance_csv_rows(
    caller: AuthorizationContext,
    employees: Select[tuple[Employee]],
    period: DateRange,
    settings: Settings,
    today: date,
) -> Iterator[AttendanceCsvRow]:
    last_id = 0
    while True:
        batch = list(
            caller.session.scalars(
                employees.where(Employee.id > last_id)
                .options(joinedload(Employee.team))
                .order_by(Employee.id)
                .limit(EMPLOYEE_BATCH_SIZE)
            )
        )
        if not batch:
            return
        employee_ids = [employee.id for employee in batch]
        rows = attendance_rows(caller.session, employee_ids, period)
        leaves = approved_leave_days(caller.session, employee_ids, period, settings)
        for employee in batch:
            identity = employee_identity(employee)
            for index in range((period.to_date - period.from_date).days + 1):
                day = period.from_date + timedelta(days=index)
                row = rows.get((employee.id, day))
                entry = calendar_entry(
                    day, row, today, settings, leaves.get((employee.id, day), [])
                )
                yield AttendanceCsvRow(
                    employee_id=employee.employee_id,
                    name=identity.name,
                    team=identity.team.name if identity.team else None,
                    date=day,
                    display_status=entry.display_status,
                    work_mode=entry.work_mode,
                    work_location=entry.work_location_name,
                    clock_in_local=entry.clock_in,
                    clock_out_local=entry.clock_out,
                    worked_hours=Decimal(str(worked_hours(row))).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    ),
                    clock_in_verified=row.clock_in_verified if row else None,
                    clock_out_verified=row.clock_out_verified if row else None,
                    clock_in_distance_m=row.clock_in_distance_m if row else None,
                    clock_out_distance_m=row.clock_out_distance_m if row else None,
                )
        last_id = batch[-1].id


def attendance_export(
    caller: AuthorizationContext, query: SelfExportQuery | AdminExportQuery, settings: Settings
) -> CsvExport:
    if isinstance(query, SelfExportQuery):
        if not has_permission(caller, "report", "export").intersection({"self", "any"}):
            raise AppError(403, "PERMISSION_DENIED", "Permission denied.")
        employees = select(Employee).where(Employee.id == caller.employee.id)
        owner = caller.employee.employee_id
    else:
        employees = admin_employees(caller, query)
        owner = "all"
    today = utc_now().astimezone(ZoneInfo(settings.app_timezone)).date()
    period = export_period(caller, query, settings, today)
    return CsvExport(
        filename=export_filename("attendance", owner, period.from_date, period.to_date),
        chunks=csv_chunks(
            AttendanceCsvRow, attendance_csv_rows(caller, employees, period, settings, today)
        ),
    )


def leave_csv_rows(
    caller: AuthorizationContext, statement: Select[tuple[LeaveRequest]], settings: Settings
) -> Iterator[LeaveCsvRow]:
    last_id = 0
    zone = ZoneInfo(settings.app_timezone)
    while True:
        rows = list(
            caller.session.scalars(
                statement.where(LeaveRequest.id > last_id)
                .order_by(LeaveRequest.id)
                .limit(LEAVE_BATCH_SIZE)
            )
        )
        if not rows:
            return
        for row in rows:
            identity = employee_identity(row.employee)
            duration = row.duration_type.value
            if row.duration_type == LeaveDuration.HALF_DAY and row.half_day_period is not None:
                duration += f" ({row.half_day_period.value})"
            yield LeaveCsvRow(
                employee_id=identity.employee_id,
                name=identity.name,
                team=identity.team.name if identity.team else None,
                leave_type=row.leave_type.name,
                reason=row.leave_reason.name,
                reason_text=row.reason_text,
                duration=duration,
                num_days=row.num_days,
                start_date=row.start_date,
                end_date=row.end_date,
                reporting_manager=employee_identity(row.reporting_manager).name,
                status=row.status,
                decided_by=employee_identity(row.decider).name if row.decider else None,
                decided_at=row.decided_at.astimezone(zone) if row.decided_at else None,
                remark=row.remark,
            )
        last_id = rows[-1].id


def leave_export(
    caller: AuthorizationContext, query: AdminExportQuery, settings: Settings
) -> CsvExport:
    employees = admin_employees(caller, query)
    today = utc_now().astimezone(ZoneInfo(settings.app_timezone)).date()
    period = export_period(caller, query, settings, today)
    statement = requests_query().where(
        LeaveRequest.employee_id.in_(employees.with_only_columns(Employee.id)),
        LeaveRequest.start_date <= period.to_date,
        LeaveRequest.end_date >= period.from_date,
    )
    return CsvExport(
        filename=export_filename("leave", "all", period.from_date, period.to_date),
        chunks=csv_chunks(LeaveCsvRow, leave_csv_rows(caller, statement, settings)),
    )

from datetime import date
from zoneinfo import ZoneInfo

from app.core.config import Settings
from app.models import Attendance, Employee
from app.schemas.attendance import (
    AttendanceResponse,
    AttendanceSummary,
    CalendarEntry,
    DisplayStatus,
    EmployeeIdentity,
    GpsEvidence,
)
from app.schemas.auth import TeamSummary


def worked_hours(row: Attendance | None) -> float:
    if row is None or row.clock_in is None or row.clock_out is None:
        return 0
    return (row.clock_out - row.clock_in).total_seconds() / 3600


def employee_identity(employee: Employee) -> EmployeeIdentity:
    return EmployeeIdentity(
        id=employee.id,
        employee_id=employee.employee_id,
        name=employee.display_name or f"{employee.first_name} {employee.last_name}",
        team=TeamSummary(id=employee.team.id, name=employee.team.name) if employee.team else None,
    )


def evidence(row: Attendance, action: str) -> GpsEvidence:
    return GpsEvidence(
        **{
            field: getattr(row, f"{action}_{field}")
            for field in (
                "latitude",
                "longitude",
                "accuracy_m",
                "distance_m",
                "verified",
            )
        }
    )


def attendance_response(row: Attendance, settings: Settings) -> AttendanceResponse:
    zone = ZoneInfo(settings.app_timezone)
    return AttendanceResponse(
        id=row.id,
        employee_id=row.employee_id,
        attendance_date=row.attendance_date,
        work_mode=row.work_mode,
        work_location_id=row.work_location_id,
        work_location_name=row.work_location.name if row.work_location else None,
        clock_in=row.clock_in.astimezone(zone) if row.clock_in else None,
        clock_out=row.clock_out.astimezone(zone) if row.clock_out else None,
        clock_in_gps=evidence(row, "clock_in"),
        clock_out_gps=evidence(row, "clock_out"),
        status=row.status,
        updated_by=row.updated_by,
        worked_hours=round(worked_hours(row), 4),
        created_at=row.created_at.astimezone(zone),
        updated_at=row.updated_at.astimezone(zone),
    )


def calendar_entry(
    day: date, row: Attendance | None, today: date, settings: Settings
) -> CalendarEntry:
    if day > today:
        status: DisplayStatus | None = "upcoming"
    elif row is not None:
        status = row.status.value
    elif day.weekday() not in settings.working_weekday_numbers:
        status = "weekend"
    elif day < today:
        status = "absent"
    else:
        status = None
    zone = ZoneInfo(settings.app_timezone)
    return CalendarEntry(
        date=day,
        attendance_id=row.id if row else None,
        display_status=status,
        work_mode=row.work_mode if row else None,
        clock_in=row.clock_in.astimezone(zone) if row and row.clock_in else None,
        clock_out=row.clock_out.astimezone(zone) if row and row.clock_out else None,
        work_location_name=row.work_location.name if row and row.work_location else None,
        worked_hours=round(worked_hours(row), 4),
    )


def summarize(entries: list[CalendarEntry]) -> AttendanceSummary:
    return AttendanceSummary(
        present_days=sum(entry.display_status == "present" for entry in entries),
        half_day_days=sum(entry.display_status == "half-day" for entry in entries),
        leave_days=sum(entry.display_status == "leave" for entry in entries),
        absent_days=sum(entry.display_status == "absent" for entry in entries),
        total_worked_hours=round(sum(entry.worked_hours for entry in entries), 2),
    )

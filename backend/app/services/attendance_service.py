import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.core.errors import AppError
from app.models import Attendance, Employee, TeamWorkLocation, WorkLocation
from app.models.enums import AttendanceStatus, WorkMode
from app.schemas.attendance import (
    AttendanceResponse,
    AttendanceUpdate,
    ClockRequest,
    ClockResponse,
    TodayResponse,
)
from app.services.admin_support import audit, get_entity
from app.services.attendance_presenter import attendance_response, worked_hours
from app.services.authorization_service import AuthorizationContext, authorize, has_permission
from app.services.gps_service import GpsResult, verify_onsite
from app.utils.time import utc_now

logger = logging.getLogger(__name__)


@contextmanager
def attendance_transaction(caller: AuthorizationContext) -> Iterator[None]:
    try:
        yield
        caller.session.commit()
    except IntegrityError as exc:
        caller.session.rollback()
        raise AppError(409, "ATTENDANCE_CONFLICT", "Attendance changed; reload and retry.") from exc
    except Exception:
        caller.session.rollback()
        raise


def todays_row(
    caller: AuthorizationContext, employee_id: int, day: date, *, lock: bool = False
) -> Attendance | None:
    statement = (
        select(Attendance)
        .where(Attendance.employee_id == employee_id, Attendance.attendance_date == day)
        .execution_options(populate_existing=True)
    )
    if lock:
        statement = statement.with_for_update()
    return caller.session.scalar(statement)


def today(caller: AuthorizationContext, settings: Settings) -> TodayResponse:
    authorize(caller, "attendance", "read", caller.employee)
    day = utc_now().astimezone(ZoneInfo(settings.app_timezone)).date()
    row = todays_row(caller, caller.employee.id, day)
    action: Literal["clock_in", "clock_out", "none"] = "clock_in"
    if row and row.clock_out is not None:
        action = "none"
    elif row and row.clock_in is not None:
        action = "clock_out"
    return TodayResponse(
        date=day, attendance=attendance_response(row, settings) if row else None, next_action=action
    )


def gps_for_action(
    caller: AuthorizationContext, employee: Employee, data: ClockRequest, settings: Settings
) -> GpsResult:
    locations = (
        caller.session.scalars(
            select(WorkLocation)
            .join(TeamWorkLocation, TeamWorkLocation.work_location_id == WorkLocation.id)
            .where(TeamWorkLocation.team_id == employee.team_id)
        ).all()
        if employee.team_id is not None
        else []
    )
    try:
        return verify_onsite(locations, data.latitude, data.longitude, data.accuracy_m, settings)
    except AppError as error:
        logger.warning(
            "Onsite verification rejected employee_id=%s code=%s distance_m=%s accuracy_m=%s",
            employee.employee_id,
            error.code,
            (error.details or {}).get("distance_m"),
            data.accuracy_m,
        )
        raise


def set_gps(row: Attendance, action: str, data: ClockRequest, result: GpsResult | None) -> None:
    if result is None:
        clear_gps(row, action)
        return
    assert data.latitude is not None and data.longitude is not None and data.accuracy_m is not None
    setattr(row, f"{action}_latitude", Decimal(str(data.latitude)).quantize(Decimal("0.000001")))
    setattr(row, f"{action}_longitude", Decimal(str(data.longitude)).quantize(Decimal("0.000001")))
    setattr(row, f"{action}_accuracy_m", Decimal(str(data.accuracy_m)).quantize(Decimal("0.01")))
    setattr(row, f"{action}_distance_m", result.distance_m)
    setattr(row, f"{action}_verified", result.verified)


def clear_gps(row: Attendance, action: str) -> None:
    for field in ("latitude", "longitude", "accuracy_m", "distance_m", "verified"):
        setattr(row, f"{action}_{field}", None)


def clock(
    caller: AuthorizationContext, data: ClockRequest, settings: Settings, *, clock_out: bool
) -> ClockResponse:
    authorize(caller, "attendance", "create", caller.employee)
    with attendance_transaction(caller):
        employee = get_entity(caller.session, Employee, caller.employee.id, lock=True)
        if not employee.is_active:
            raise AppError(401, "INVALID_TOKEN", "Invalid authentication token.")
        if employee.must_change_password:
            raise AppError(
                403, "PASSWORD_CHANGE_REQUIRED", "Change your password before continuing."
            )
        now = utc_now()
        zone = ZoneInfo(settings.app_timezone)
        day = now.astimezone(zone).date()
        row = todays_row(caller, employee.id, day, lock=True)
        if clock_out:
            if row is None or row.clock_in is None:
                raise AppError(409, "NOT_CLOCKED_IN", "Clock in before clocking out today.")
            if row.clock_out is not None:
                raise AppError(409, "ALREADY_CLOCKED_OUT", "You have already clocked out today.")
            if now < row.clock_in:
                raise AppError(
                    409, "CLOCK_TIME_CONFLICT", "Server time precedes clock-in; retry later."
                )
            mode = row.work_mode
        else:
            if row and row.clock_in is not None:
                raise AppError(409, "ALREADY_CLOCKED_IN", "You have already clocked in today.")
            mode = data.work_mode
        gps = gps_for_action(caller, employee, data, settings) if mode == WorkMode.ONSITE else None
        if row is None:
            row = Attendance(
                employee_id=employee.id,
                attendance_date=day,
                work_mode=mode,
                status=AttendanceStatus.PRESENT,
            )
            caller.session.add(row)
        if clock_out:
            row.clock_out = now
            set_gps(row, "clock_out", data, gps)
            row.status = (
                AttendanceStatus.HALF_DAY
                if worked_hours(row) < settings.half_day_threshold_hours
                else AttendanceStatus.PRESENT
            )
            minutes = int((now - row.clock_in).total_seconds() // 60) if row.clock_in else 0
            message = (
                f"Clocked out at {now.astimezone(zone):%H:%M}. "
                f"Worked {minutes // 60}h {minutes % 60:02d}m."
            )
        else:
            row.work_mode = mode
            row.work_location_id = gps.location_id if gps else None
            row.clock_in = now
            row.clock_out = None
            row.status = AttendanceStatus.PRESENT
            set_gps(row, "clock_in", data, gps)
            clear_gps(row, "clock_out")
            caller.session.flush()
            caller.session.expire(row, ["work_location"])
            label = f"Onsite – {row.work_location.name}" if row.work_location else "Remote"
            message = f"Clocked in at {now.astimezone(zone):%H:%M} ({label})."
        caller.session.flush()
        caller.session.refresh(row)
        return ClockResponse(attendance=attendance_response(row, settings), message=message)


def update_attendance(
    caller: AuthorizationContext, attendance_id: int, data: AttendanceUpdate, settings: Settings
) -> AttendanceResponse:
    if not has_permission(caller, "attendance", "update").intersection({"team", "any"}):
        raise AppError(403, "PERMISSION_DENIED", "Permission denied.")
    with attendance_transaction(caller):
        initial = get_entity(caller.session, Attendance, attendance_id)
        employee = get_entity(caller.session, Employee, initial.employee_id, lock=True)
        authorize(caller, "attendance", "update", employee)
        row = get_entity(caller.session, Attendance, attendance_id, lock=True)
        before = attendance_response(row, settings).model_dump(mode="json")
        new_in = data.clock_in if "clock_in" in data.model_fields_set else row.clock_in
        new_out = data.clock_out if "clock_out" in data.model_fields_set else row.clock_out
        now = utc_now()
        zone = ZoneInfo(settings.app_timezone)
        if (new_out is not None and (new_in is None or new_out < new_in)) or any(
            value > now or value.astimezone(zone).date() != row.attendance_date
            for value in (new_in, new_out)
            if value is not None
        ):
            raise AppError(
                422,
                "INVALID_CLOCK_TIMES",
                "Clock times must be ordered, not in the future, and on the attendance date.",
            )
        for field in ("clock_in", "clock_out"):
            if field in data.model_fields_set and getattr(row, field) != getattr(data, field):
                setattr(row, field, getattr(data, field))
                clear_gps(row, field)
        if row.clock_in is None:
            row.work_location_id = None
        if data.status is not None:
            row.status = data.status
        row.updated_by = caller.employee.id
        caller.session.flush()
        caller.session.refresh(row)
        response = attendance_response(row, settings)
        audit(
            caller,
            "attendance.update",
            "attendance",
            row.id,
            before,
            {**response.model_dump(mode="json"), "reason": data.reason},
        )
        return response

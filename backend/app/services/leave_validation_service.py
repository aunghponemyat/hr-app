from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.models import LeaveRequest
from app.models.enums import LeaveDuration, LeaveStatus
from app.schemas.leave import LeaveCreate


def compute_end_date(data: LeaveCreate, today: date, settings: Settings) -> date:
    if data.num_days > settings.leave_max_days_per_request:
        raise AppError(
            422, "LEAVE_TOO_LONG", f"Select at most {settings.leave_max_days_per_request} days."
        )
    if data.start_date < today - timedelta(days=settings.leave_backdate_days):
        raise AppError(422, "LEAVE_BACKDATE_LIMIT", "The start date is too far in the past.")
    if data.start_date.weekday() not in settings.working_weekday_numbers:
        raise AppError(422, "NON_WORKING_DAY", "Leave must start on a working day.")
    end = data.start_date
    remaining = int(data.num_days) - 1 if data.duration_type == LeaveDuration.FULL_DAYS else 0
    try:
        while remaining:
            end += timedelta(days=1)
            if end.weekday() in settings.working_weekday_numbers:
                remaining -= 1
    except OverflowError as exc:
        raise AppError(
            422, "INVALID_LEAVE_DATES", "Leave dates exceed the supported calendar."
        ) from exc
    return end


def check_overlap(session: Session, employee_id: int, data: LeaveCreate, end_date: date) -> None:
    # Locking reads see requests committed while waiting on the requester lock.
    rows = session.scalars(
        select(LeaveRequest)
        .where(
            LeaveRequest.employee_id == employee_id,
            LeaveRequest.status.in_([LeaveStatus.PENDING, LeaveStatus.APPROVED]),
            LeaveRequest.start_date <= end_date,
            LeaveRequest.end_date >= data.start_date,
        )
        .with_for_update()
    )
    for row in rows:
        if (
            row.duration_type == data.duration_type == LeaveDuration.HALF_DAY
            and row.start_date == data.start_date
            and row.half_day_period != data.half_day_period
        ):
            continue
        raise AppError(
            409, "LEAVE_OVERLAP", "This period overlaps a pending or approved leave request."
        )

from datetime import date, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings
from app.models import LeaveRequest
from app.models.enums import HalfDayPeriod, LeaveDuration, LeaveStatus
from app.schemas.attendance import DateRange, LeaveInfo


def approved_leave_days(
    session: Session, employee_ids: list[int], period: DateRange, settings: Settings
) -> dict[tuple[int, date], list[LeaveInfo]]:
    if not employee_ids:
        return {}
    rows = session.scalars(
        select(LeaveRequest)
        .where(
            LeaveRequest.employee_id.in_(employee_ids),
            LeaveRequest.status == LeaveStatus.APPROVED,
            LeaveRequest.start_date <= period.to_date,
            LeaveRequest.end_date >= period.from_date,
        )
        .options(joinedload(LeaveRequest.leave_type))
        .order_by(LeaveRequest.id)
        .execution_options(populate_existing=True)
    )
    days: dict[tuple[int, date], list[LeaveInfo]] = {}
    for row in rows:
        start, end = max(row.start_date, period.from_date), min(row.end_date, period.to_date)
        info = LeaveInfo(
            id=row.id,
            leave_type=row.leave_type.name,
            duration_type=row.duration_type,
            half_day_period=row.half_day_period,
            status=row.status,
        )
        for index in range((end - start).days + 1):
            day = start + timedelta(days=index)
            if day.weekday() in settings.working_weekday_numbers:
                days.setdefault((row.employee_id, day), []).append(info)
    return days


def leave_display_status(leaves: list[LeaveInfo]) -> Literal["leave", "half-day"] | None:
    if not leaves:
        return None
    halves = {leave.half_day_period for leave in leaves}
    if any(leave.duration_type == LeaveDuration.FULL_DAYS for leave in leaves) or {
        HalfDayPeriod.MORNING,
        HalfDayPeriod.AFTERNOON,
    }.issubset(halves):
        return "leave"
    return "half-day"


def leave_years(session: Session, employee_id: int, earliest: date | None) -> set[int]:
    query = select(LeaveRequest.start_date, LeaveRequest.end_date).where(
        LeaveRequest.employee_id == employee_id, LeaveRequest.status == LeaveStatus.APPROVED
    )
    if earliest is not None:
        query = query.where(LeaveRequest.end_date >= earliest)
    years: set[int] = set()
    for start, end in session.execute(query):
        if earliest is not None:
            start = max(start, earliest)
        years.update(range(start.year, end.year + 1))
    return years

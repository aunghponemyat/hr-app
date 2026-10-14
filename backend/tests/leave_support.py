from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Employee, LeaveReason, LeaveRequest, LeaveType
from app.models.enums import HalfDayPeriod, LeaveDuration, LeaveStatus


def leave_payload(session: Session, manager: Employee, **changes: Any) -> dict[str, Any]:
    type_id = session.scalar(select(LeaveType.id).where(LeaveType.code == "annual"))
    reason_id = session.scalar(select(LeaveReason.id).where(LeaveReason.code == "vacation"))
    return {
        "leave_type_id": type_id,
        "leave_reason_id": reason_id,
        "duration_type": "full_days",
        "num_days": 2,
        "start_date": "2026-10-16",
        "reporting_manager_id": manager.id,
        **changes,
    }


def leave_record(
    session: Session,
    employee: Employee,
    manager: Employee,
    *,
    day: date = date(2026, 10, 14),
    end: date | None = None,
    status: LeaveStatus = LeaveStatus.PENDING,
    half: HalfDayPeriod | None = None,
) -> LeaveRequest:
    type_id = session.scalar(select(LeaveType.id).where(LeaveType.code == "annual"))
    reason_id = session.scalar(select(LeaveReason.id).where(LeaveReason.code == "vacation"))
    assert type_id is not None and reason_id is not None
    return LeaveRequest(
        employee_id=employee.id,
        reporting_manager_id=manager.id,
        leave_type_id=type_id,
        leave_reason_id=reason_id,
        status=status,
        duration_type=LeaveDuration.HALF_DAY if half else LeaveDuration.FULL_DAYS,
        half_day_period=half,
        num_days=Decimal("0.5") if half else Decimal("1"),
        start_date=day,
        end_date=end or day,
    )

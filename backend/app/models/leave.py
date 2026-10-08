from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    text,
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TABLE_OPTIONS, Base, IdMixin, TimestampMixin, UTCDateTime
from app.models.enums import HalfDayPeriod, LeaveDuration, LeaveStatus, enum_values

if TYPE_CHECKING:
    from app.models.employee import Employee


class LeaveType(IdMixin, Base):
    __tablename__ = "leave_types"

    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("1"))


class LeaveReason(IdMixin, Base):
    __tablename__ = "leave_reasons"

    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    requires_text: Mapped[bool] = mapped_column(Boolean, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("1"))


class LeaveRequest(IdMixin, TimestampMixin, Base):
    __tablename__ = "leave_requests"
    __table_args__ = (
        Index("ix_leave_requests_employee_start", "employee_id", "start_date"),
        Index("ix_leave_requests_manager_status", "reporting_manager_id", "status"),
        Index("ix_leave_requests_status", "status"),
        CheckConstraint("end_date >= start_date", name="date_order"),
        CheckConstraint("reporting_manager_id <> employee_id", name="manager_not_requester"),
        CheckConstraint("decided_by IS NULL OR decided_by <> employee_id", name="no_self_decision"),
        CheckConstraint(
            "(duration_type = 'half_day' AND num_days = 0.5 AND half_day_period IS NOT NULL "
            "AND end_date = start_date) OR (duration_type = 'full_days' AND num_days >= 1 "
            "AND num_days = FLOOR(num_days) AND half_day_period IS NULL)",
            name="valid_duration",
        ),
        TABLE_OPTIONS,
    )

    employee_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), ForeignKey("employees.id"))
    leave_type_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), ForeignKey("leave_types.id"))
    leave_reason_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("leave_reasons.id")
    )
    reason_text: Mapped[str | None] = mapped_column(String(500))
    duration_type: Mapped[LeaveDuration] = mapped_column(
        Enum(LeaveDuration, values_callable=enum_values)
    )
    half_day_period: Mapped[HalfDayPeriod | None] = mapped_column(
        Enum(HalfDayPeriod, values_callable=enum_values)
    )
    num_days: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    reporting_manager_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("employees.id")
    )
    remark: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[LeaveStatus] = mapped_column(
        Enum(LeaveStatus, values_callable=enum_values), server_default=text("'pending'")
    )
    decided_by: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("employees.id")
    )
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    decision_note: Mapped[str | None] = mapped_column(String(500))
    employee: Mapped[Employee] = relationship(foreign_keys=[employee_id])
    reporting_manager: Mapped[Employee] = relationship(foreign_keys=[reporting_manager_id])
    decider: Mapped[Employee | None] = relationship(foreign_keys=[decided_by])
    leave_type: Mapped[LeaveType] = relationship()
    leave_reason: Mapped[LeaveReason] = relationship()

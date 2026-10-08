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
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TABLE_OPTIONS, Base, IdMixin, TimestampMixin, UTCDateTime
from app.models.enums import AttendanceStatus, WorkMode, enum_values

if TYPE_CHECKING:
    from app.models.employee import Employee
    from app.models.location import WorkLocation


class Attendance(IdMixin, TimestampMixin, Base):
    __tablename__ = "attendance"
    __table_args__ = (
        UniqueConstraint("employee_id", "attendance_date"),
        Index("ix_attendance_attendance_date", "attendance_date"),
        CheckConstraint(
            "clock_out IS NULL OR (clock_in IS NOT NULL AND clock_out >= clock_in)",
            name="clock_order",
        ),
        *(
            CheckConstraint(f"{action}_latitude BETWEEN -90 AND 90", name=f"{action}_latitude")
            for action in ("clock_in", "clock_out")
        ),
        *(
            CheckConstraint(f"{action}_longitude BETWEEN -180 AND 180", name=f"{action}_longitude")
            for action in ("clock_in", "clock_out")
        ),
        *(
            CheckConstraint(f"{action}_{field}_m >= 0", name=f"{action}_{field}")
            for action in ("clock_in", "clock_out")
            for field in ("accuracy", "distance")
        ),
        TABLE_OPTIONS,
    )

    employee_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), ForeignKey("employees.id"))
    attendance_date: Mapped[date] = mapped_column(Date)
    work_mode: Mapped[WorkMode] = mapped_column(Enum(WorkMode, values_callable=enum_values))
    work_location_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("work_locations.id")
    )
    clock_in: Mapped[datetime | None] = mapped_column(UTCDateTime())
    clock_out: Mapped[datetime | None] = mapped_column(UTCDateTime())
    clock_in_latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    clock_in_longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    clock_in_accuracy_m: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    clock_in_distance_m: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    clock_in_verified: Mapped[bool | None] = mapped_column(Boolean)
    clock_out_latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    clock_out_longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    clock_out_accuracy_m: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    clock_out_distance_m: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    clock_out_verified: Mapped[bool | None] = mapped_column(Boolean)
    status: Mapped[AttendanceStatus] = mapped_column(
        Enum(AttendanceStatus, values_callable=enum_values)
    )
    updated_by: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("employees.id")
    )
    employee: Mapped[Employee] = relationship(foreign_keys=[employee_id])
    editor: Mapped[Employee | None] = relationship(foreign_keys=[updated_by])
    work_location: Mapped[WorkLocation | None] = relationship()

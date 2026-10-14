from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import AttendanceStatus, HalfDayPeriod, LeaveDuration, LeaveStatus, WorkMode
from app.schemas.admin import PageQuery, PositiveId
from app.schemas.auth import TeamSummary
from app.schemas.common import RequestSchema

DisplayStatus = Literal["present", "absent", "half-day", "leave", "weekend", "upcoming"]


class ClockRequest(RequestSchema):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True, allow_inf_nan=False)
    work_mode: WorkMode
    latitude: float | None = None
    longitude: float | None = None
    accuracy_m: float | None = None


class AttendanceUpdate(RequestSchema):
    status: AttendanceStatus | None = None
    clock_in: datetime | None = None
    clock_out: datetime | None = None
    reason: str = Field(min_length=1, max_length=500, pattern=r"\S")

    @field_validator("clock_in", "clock_out")
    @classmethod
    def offset_required(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Clock times must include a timezone offset.")
        return value

    @model_validator(mode="after")
    def validate_edit(self) -> "AttendanceUpdate":
        if not self.model_fields_set.intersection({"status", "clock_in", "clock_out"}):
            raise ValueError("Provide at least one attendance field to update.")
        if "status" in self.model_fields_set and self.status is None:
            raise ValueError("Status cannot be null.")
        return self


class PeriodQuery(RequestSchema):
    view: Literal["week", "month", "year", "custom"] | None = Field(
        default=None,
        description="Defaults to the current month, or custom when from/to are supplied.",
    )
    anchor: date | None = None
    from_date: date | None = Field(default=None, alias="from")
    to_date: date | None = Field(default=None, alias="to")

    @model_validator(mode="after")
    def validate_period(self) -> "PeriodQuery":
        if self.from_date is not None or self.to_date is not None:
            if self.from_date is None or self.to_date is None:
                raise ValueError("Provide both from and to dates.")
            if self.view is not None and self.view != "custom":
                raise ValueError("Date bounds require custom view.")
        if (self.view == "custom" or self.from_date is not None) and (
            self.from_date is None or self.to_date is None or self.anchor is not None
        ):
            raise ValueError("Custom view requires from/to dates and no anchor.")
        return self


class CalendarQuery(PeriodQuery):
    employee_id: PositiveId | None = None


class AttendanceQuery(CalendarQuery, PageQuery):
    pass


class TeamAttendanceQuery(PeriodQuery, PageQuery):
    pass


class GpsEvidence(BaseModel):
    latitude: Decimal | None
    longitude: Decimal | None
    accuracy_m: Decimal | None
    distance_m: Decimal | None
    verified: bool | None


class AttendanceResponse(BaseModel):
    id: int
    employee_id: int
    attendance_date: date
    work_mode: WorkMode
    work_location_id: int | None
    work_location_name: str | None
    clock_in: datetime | None
    clock_out: datetime | None
    clock_in_gps: GpsEvidence
    clock_out_gps: GpsEvidence
    status: AttendanceStatus
    updated_by: int | None
    worked_hours: float
    created_at: datetime
    updated_at: datetime


class ClockResponse(BaseModel):
    attendance: AttendanceResponse
    message: str


class TodayResponse(BaseModel):
    date: date
    attendance: AttendanceResponse | None
    next_action: Literal["clock_in", "clock_out", "none"]


class LeaveInfo(BaseModel):
    id: int
    leave_type: str
    duration_type: LeaveDuration
    half_day_period: HalfDayPeriod | None
    status: LeaveStatus


class CalendarEntry(BaseModel):
    date: date
    attendance_id: int | None
    display_status: DisplayStatus | None
    work_mode: WorkMode | None
    clock_in: datetime | None
    clock_out: datetime | None
    work_location_name: str | None
    worked_hours: float
    leave: LeaveInfo | None = None


class AttendanceSummary(BaseModel):
    present_days: int = 0
    half_day_days: int = 0
    leave_days: int = 0
    absent_days: int = 0
    total_worked_hours: float = 0


class EmployeeIdentity(BaseModel):
    id: int
    employee_id: str
    name: str
    team: TeamSummary | None


class DateRange(BaseModel):
    from_date: date
    to_date: date


class CalendarResponse(BaseModel):
    employee: EmployeeIdentity
    period: DateRange
    entries: list[CalendarEntry]
    summary: AttendanceSummary
    available_years: list[int]


class AttendanceTableRow(CalendarEntry):
    employee: EmployeeIdentity


class AttendanceTableResponse(BaseModel):
    items: list[AttendanceTableRow]
    total: int
    page: int
    page_size: int
    period: DateRange


class TeamAttendanceRow(BaseModel):
    employee: EmployeeIdentity
    summary: AttendanceSummary


class TeamAttendanceResponse(BaseModel):
    items: list[TeamAttendanceRow]
    total: int
    page: int
    page_size: int
    period: DateRange

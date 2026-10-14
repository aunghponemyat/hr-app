from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import HalfDayPeriod, LeaveDuration, LeaveStatus
from app.schemas.admin import PageQuery, PositiveId
from app.schemas.attendance import EmployeeIdentity
from app.schemas.common import RequestSchema


class LeaveCreate(RequestSchema):
    leave_type_id: PositiveId
    leave_reason_id: PositiveId
    reason_text: str | None = Field(default=None, max_length=500)
    duration_type: LeaveDuration
    half_day_period: HalfDayPeriod | None = None
    num_days: Decimal = Field(ge=0.5, le=99, max_digits=4, decimal_places=1)
    start_date: date
    reporting_manager_id: PositiveId
    remark: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_duration(self) -> "LeaveCreate":
        if self.duration_type == LeaveDuration.HALF_DAY:
            if self.half_day_period is None or self.num_days != Decimal("0.5"):
                raise ValueError("Half-day leave requires a period and exactly 0.5 days.")
        elif (
            self.half_day_period is not None
            or self.num_days != self.num_days.to_integral_value()
            or self.num_days < 1
        ):
            raise ValueError("Full-day leave requires an integer day count and no half-day period.")
        return self


class LeaveDecision(RequestSchema):
    decision_note: str | None = Field(default=None, max_length=500)


class LeaveQuery(PageQuery):
    status: LeaveStatus | None = None


class TeamLeaveQuery(LeaveQuery):
    employee_id: PositiveId | None = None


class LeaveChoice(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str


class LeaveReasonChoice(LeaveChoice):
    requires_text: bool


class LeaveOptions(BaseModel):
    types: list[LeaveChoice]
    reasons: list[LeaveReasonChoice]
    managers: list[EmployeeIdentity]
    today: date
    working_weekdays: list[int]
    max_days_per_request: int
    backdate_days: int


class LeaveResponse(BaseModel):
    id: int
    employee: EmployeeIdentity
    leave_type: LeaveChoice
    leave_reason: LeaveReasonChoice
    reason_text: str | None
    duration_type: LeaveDuration
    half_day_period: HalfDayPeriod | None
    num_days: Decimal
    start_date: date
    end_date: date
    reporting_manager: EmployeeIdentity
    remark: str | None
    status: LeaveStatus
    decided_by: EmployeeIdentity | None
    decided_at: datetime | None
    decision_note: str | None
    created_at: datetime
    updated_at: datetime

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, RootModel, model_validator

from app.models.enums import LeaveStatus, WorkMode
from app.schemas.admin import PositiveId
from app.schemas.attendance import DisplayStatus
from app.schemas.common import RequestSchema


class SelfExportQuery(RequestSchema):
    from_date: date = Field(alias="from")
    to_date: date = Field(alias="to")


class AdminExportQuery(RequestSchema):
    from_date: date | None = Field(default=None, alias="from")
    to_date: date | None = Field(default=None, alias="to")
    team_id: PositiveId | None = None
    employee_id: PositiveId | None = None

    @model_validator(mode="after")
    def require_paired_dates(self) -> "AdminExportQuery":
        if (self.from_date is None) != (self.to_date is None):
            raise ValueError("Provide both from and to, or omit both for the current month.")
        return self


class CsvDocument(RootModel[str]):
    """UTF-8 CSV text with a leading BOM and Section 10.7's ordered column header."""


class AttendanceCsvRow(BaseModel):
    employee_id: str
    name: str
    team: str | None
    date: date
    display_status: DisplayStatus | None
    work_mode: WorkMode | None
    work_location: str | None
    clock_in_local: datetime | None
    clock_out_local: datetime | None
    worked_hours: Decimal
    clock_in_verified: bool | None
    clock_out_verified: bool | None
    clock_in_distance_m: Decimal | None
    clock_out_distance_m: Decimal | None


class LeaveCsvRow(BaseModel):
    employee_id: str
    name: str
    team: str | None
    leave_type: str
    reason: str
    reason_text: str | None
    duration: str
    num_days: Decimal
    start_date: date
    end_date: date
    reporting_manager: str
    status: LeaveStatus
    decided_by: str | None
    decided_at: datetime | None
    remark: str | None

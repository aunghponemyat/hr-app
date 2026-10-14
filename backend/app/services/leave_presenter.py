from zoneinfo import ZoneInfo

from app.core.config import Settings
from app.models import LeaveRequest
from app.schemas.leave import LeaveChoice, LeaveReasonChoice, LeaveResponse
from app.services.attendance_presenter import employee_identity


def leave_response(row: LeaveRequest, settings: Settings) -> LeaveResponse:
    zone = ZoneInfo(settings.app_timezone)
    return LeaveResponse(
        id=row.id,
        employee=employee_identity(row.employee),
        leave_type=LeaveChoice.model_validate(row.leave_type),
        leave_reason=LeaveReasonChoice.model_validate(row.leave_reason),
        reason_text=row.reason_text,
        duration_type=row.duration_type,
        half_day_period=row.half_day_period,
        num_days=row.num_days,
        start_date=row.start_date,
        end_date=row.end_date,
        reporting_manager=employee_identity(row.reporting_manager),
        remark=row.remark,
        status=row.status,
        decided_by=employee_identity(row.decider) if row.decider else None,
        decided_at=row.decided_at.astimezone(zone) if row.decided_at else None,
        decision_note=row.decision_note,
        created_at=row.created_at.astimezone(zone),
        updated_at=row.updated_at.astimezone(zone),
    )

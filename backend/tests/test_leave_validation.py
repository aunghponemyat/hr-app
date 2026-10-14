from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import LeaveReason, LeaveRequest, LeaveType
from app.models.enums import LeaveStatus
from app.schemas.leave import LeaveCreate
from app.services.leave_validation_service import compute_end_date
from tests.attendance_support import AttendanceClock
from tests.authz_support import AuthzScenario
from tests.leave_support import leave_payload, leave_record
from tests.test_auth import bearer, login_token


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"duration_type": "half_day", "num_days": 0.5}, "VALIDATION_ERROR"),
        (
            {"duration_type": "half_day", "num_days": 1, "half_day_period": "morning"},
            "VALIDATION_ERROR",
        ),
        ({"num_days": 0.5}, "VALIDATION_ERROR"),
        ({"num_days": 1.5}, "VALIDATION_ERROR"),
        ({"num_days": 0}, "VALIDATION_ERROR"),
        ({"num_days": 31}, "LEAVE_TOO_LONG"),
        ({"half_day_period": "morning"}, "VALIDATION_ERROR"),
        ({"remark": "x" * 501}, "VALIDATION_ERROR"),
        ({"reason_text": "x" * 501}, "VALIDATION_ERROR"),
        ({"start_date": "2026-10-06"}, "LEAVE_BACKDATE_LIMIT"),
        ({"start_date": "2026-10-17"}, "NON_WORKING_DAY"),
        ({"employee_id": 1}, "VALIDATION_ERROR"),
        ({"end_date": "2026-11-01"}, "VALIDATION_ERROR"),
        ({"status": "approved"}, "VALIDATION_ERROR"),
        ({"decided_at": "2026-10-14T02:00:00Z"}, "VALIDATION_ERROR"),
        ({"reporting_manager_id": 2**63}, "INELIGIBLE_MANAGER"),
    ],
)
def test_leave_validation_is_atomic(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
    changes: dict[str, Any],
    code: str,
) -> None:
    headers = bearer(login_token(auth_client, scenario.employees["employee_a"], initial_password))
    response = auth_client.post(
        "/api/v1/leave-requests",
        headers=headers,
        json=leave_payload(seeded_session, scenario.employees["manager_a"], **changes),
    )
    assert response.status_code == 422 and response.json()["code"] == code, response.text
    assert not seeded_session.scalars(select(LeaveRequest)).all()


@pytest.mark.parametrize(
    "reason_text,valid", [(None, False), ("", False), (" ", False), ("Detailed reason", True)]
)
def test_other_reason_requires_nonblank_text(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
    reason_text: str | None,
    valid: bool,
) -> None:
    other = seeded_session.scalar(select(LeaveReason.id).where(LeaveReason.code == "other"))
    headers = bearer(login_token(auth_client, scenario.employees["employee_a"], initial_password))
    response = auth_client.post(
        "/api/v1/leave-requests",
        headers=headers,
        json=leave_payload(
            seeded_session,
            scenario.employees["manager_a"],
            leave_reason_id=other,
            reason_text=reason_text,
        ),
    )
    assert response.status_code == (201 if valid else 422), response.text
    if not valid:
        assert response.json()["code"] == "REASON_TEXT_REQUIRED"


@pytest.mark.parametrize("option", ["type", "reason"])
def test_inactive_options_not_listed_and_cannot_be_submitted(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
    option: str,
) -> None:
    row: LeaveType | LeaveReason | None = (
        seeded_session.scalars(select(LeaveType).order_by(LeaveType.id)).first()
        if option == "type"
        else seeded_session.scalars(select(LeaveReason).order_by(LeaveReason.id)).first()
    )
    assert row is not None
    row.is_active = False
    headers = bearer(login_token(auth_client, scenario.employees["employee_a"], initial_password))
    options = auth_client.get("/api/v1/leave/options", headers=headers).json()
    assert row.id not in {
        item["id"] for item in options["types" if option == "type" else "reasons"]
    }
    response = auth_client.post(
        "/api/v1/leave-requests",
        headers=headers,
        json=leave_payload(
            seeded_session, scenario.employees["manager_a"], **{f"leave_{option}_id": row.id}
        ),
    )
    assert response.status_code == 422 and response.json()["code"] == "INACTIVE_LEAVE_OPTION"


@pytest.mark.parametrize(
    "status,overlaps",
    [
        (LeaveStatus.PENDING, True),
        (LeaveStatus.APPROVED, True),
        (LeaveStatus.REJECTED, False),
        (LeaveStatus.CANCELLED, False),
    ],
)
def test_full_day_overlap_only_blocks_pending_and_approved(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
    status: LeaveStatus,
    overlaps: bool,
) -> None:
    seeded_session.add(
        leave_record(
            seeded_session,
            scenario.employees["employee_a"],
            scenario.employees["manager_a"],
            day=date(2026, 10, 16),
            end=date(2026, 10, 19),
            status=status,
        )
    )
    headers = bearer(login_token(auth_client, scenario.employees["employee_a"], initial_password))
    response = auth_client.post(
        "/api/v1/leave-requests",
        headers=headers,
        json=leave_payload(
            seeded_session, scenario.employees["manager_a"], start_date="2026-10-19", num_days=1
        ),
    )
    assert response.status_code == (409 if overlaps else 201), response.text
    if overlaps:
        assert response.json()["code"] == "LEAVE_OVERLAP"


def test_opposite_half_days_allowed_same_half_or_full_day_overlap_rejected(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
) -> None:
    headers = bearer(login_token(auth_client, scenario.employees["employee_a"], initial_password))
    half = leave_payload(
        seeded_session,
        scenario.employees["manager_a"],
        duration_type="half_day",
        num_days=0.5,
        half_day_period="morning",
        start_date="2026-10-14",
    )
    response = auth_client.post("/api/v1/leave-requests", headers=headers, json=half)
    assert response.status_code == 201 and response.json()["end_date"] == "2026-10-14"
    assert (
        auth_client.post("/api/v1/leave-requests", headers=headers, json=half).json()["code"]
        == "LEAVE_OVERLAP"
    )
    assert (
        auth_client.post(
            "/api/v1/leave-requests", headers=headers, json={**half, "half_day_period": "afternoon"}
        ).status_code
        == 201
    )
    full = leave_payload(
        seeded_session, scenario.employees["manager_a"], num_days=1, start_date="2026-10-14"
    )
    assert (
        auth_client.post("/api/v1/leave-requests", headers=headers, json=full).json()["code"]
        == "LEAVE_OVERLAP"
    )


def test_exact_backdate_limit_is_allowed_and_configured_saturday_counts(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
    auth_settings: Settings,
) -> None:
    headers = bearer(login_token(auth_client, scenario.employees["employee_a"], initial_password))
    response = auth_client.post(
        "/api/v1/leave-requests",
        headers=headers,
        json=leave_payload(
            seeded_session, scenario.employees["manager_a"], start_date="2026-10-07", num_days=1
        ),
    )
    assert response.status_code == 201
    auth_settings.working_weekdays = "0,1,2,3,4,5"
    response = auth_client.post(
        "/api/v1/leave-requests",
        headers=headers,
        json=leave_payload(
            seeded_session, scenario.employees["manager_a"], start_date="2026-10-16", num_days=3
        ),
    )
    assert response.status_code == 201 and response.json()["end_date"] == "2026-10-19"


def test_end_date_working_days_and_calendar_overflow(
    seeded_session: Session, scenario: AuthzScenario, auth_settings: Settings
) -> None:
    payload = leave_payload(
        seeded_session, scenario.employees["manager_a"], start_date="9999-12-31", num_days=2
    )
    from app.core.errors import AppError

    with pytest.raises(AppError) as error:
        compute_end_date(LeaveCreate.model_validate(payload), date(2026, 10, 14), auth_settings)
    assert error.value.code == "INVALID_LEAVE_DATES"

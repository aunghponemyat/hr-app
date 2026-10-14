from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog
from app.models.enums import AttendanceStatus, WorkMode
from tests.attendance_support import AttendanceClock, attendance_record
from tests.authz_support import AuthzScenario
from tests.test_auth import bearer, login_token


@pytest.mark.parametrize("actor", ["employee_a", "senior", "manager_a", "hr", "c_level"])
@pytest.mark.parametrize("target", ["employee_a", "employee_b"])
def test_manual_edit_role_scope_matrix_and_audit(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
    actor: str,
    target: str,
) -> None:
    record = attendance_record(scenario.employees[target], date(2026, 10, 13))
    seeded_session.add(record)
    headers = bearer(login_token(auth_client, scenario.employees[actor], initial_password))
    response = auth_client.patch(
        f"/api/v1/attendance/{record.id}",
        headers=headers,
        json={"status": "absent", "reason": "Corrected after review"},
    )
    allowed = actor in {"hr", "c_level"} or (actor == "manager_a" and target == "employee_a")
    assert response.status_code == (200 if allowed else 403), response.text
    seeded_session.refresh(record)
    if allowed:
        assert (
            record.status == AttendanceStatus.ABSENT
            and record.updated_by == scenario.employees[actor].id
        )
        log = seeded_session.scalars(
            select(AuditLog).where(AuditLog.entity_id == record.id, AuditLog.entity == "attendance")
        ).one()
        assert log.actor_id == scenario.employees[actor].id and log.action == "attendance.update"
        assert log.before_json is not None and log.before_json["status"] == "present"
        assert log.after_json is not None and log.after_json["reason"] == "Corrected after review"
    else:
        assert record.status == AttendanceStatus.PRESENT and record.updated_by is None
        assert not seeded_session.scalars(select(AuditLog)).all()


@pytest.mark.parametrize(
    "payload,code",
    [
        ({"status": "leave", "reason": "Review"}, "VALIDATION_ERROR"),
        ({"status": None, "reason": "Review"}, "VALIDATION_ERROR"),
        ({"status": "absent"}, "VALIDATION_ERROR"),
        ({"status": "absent", "reason": " "}, "VALIDATION_ERROR"),
        ({"reason": "Review"}, "VALIDATION_ERROR"),
        ({"clock_in": "2026-10-13T09:00:00", "reason": "Review"}, "VALIDATION_ERROR"),
        ({"clock_in": None, "reason": "Review"}, "INVALID_CLOCK_TIMES"),
        ({"clock_out": "2026-10-13T08:59:59+07:00", "reason": "Review"}, "INVALID_CLOCK_TIMES"),
        ({"clock_out": "2026-10-14T08:00:00+07:00", "reason": "Review"}, "INVALID_CLOCK_TIMES"),
        (
            {
                "clock_in": "2026-10-13T10:00:00+07:00",
                "clock_out": "2026-10-13T09:00:00+07:00",
                "reason": "Review",
            },
            "INVALID_CLOCK_TIMES",
        ),
        ({"clock_in_verified": True, "reason": "Review"}, "VALIDATION_ERROR"),
    ],
)
def test_invalid_manual_corrections_leave_record_and_audit_unchanged(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
    payload: dict[str, Any],
    code: str,
) -> None:
    record = attendance_record(scenario.employees["employee_a"], date(2026, 10, 13))
    seeded_session.add(record)
    headers = bearer(login_token(auth_client, scenario.employees["hr"], initial_password))
    response = auth_client.patch(f"/api/v1/attendance/{record.id}", headers=headers, json=payload)
    assert response.status_code == 422 and response.json()["code"] == code, response.text
    seeded_session.refresh(record)
    assert record.clock_in is not None and record.clock_in.hour == 2
    assert record.updated_by is None and not seeded_session.scalars(select(AuditLog)).all()


def test_changed_clock_times_clear_gps_evidence_and_allow_clearing_times(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
) -> None:
    record = attendance_record(
        scenario.employees["employee_a"], date(2026, 10, 13), mode=WorkMode.ONSITE
    )
    record.clock_in_latitude = Decimal("13.000000")
    record.clock_in_longitude = Decimal("100.000000")
    record.clock_in_accuracy_m = Decimal("10.00")
    record.clock_in_distance_m = Decimal("0.00")
    record.clock_in_verified = True
    seeded_session.add(record)
    headers = bearer(login_token(auth_client, scenario.employees["hr"], initial_password))
    response = auth_client.patch(
        f"/api/v1/attendance/{record.id}",
        headers=headers,
        json={"clock_in": "2026-10-13T10:00:00+07:00", "reason": "Corrected arrival time"},
    )
    assert response.status_code == 200, response.text
    assert all(value is None for value in response.json()["clock_in_gps"].values())
    assert response.json()["worked_hours"] == 7
    response = auth_client.patch(
        f"/api/v1/attendance/{record.id}",
        headers=headers,
        json={
            "clock_in": None,
            "clock_out": None,
            "status": "absent",
            "reason": "Invalid record cleared",
        },
    )
    assert (
        response.status_code == 200
        and response.json()["clock_in"] is None
        and response.json()["clock_out"] is None
    )
    assert response.json()["work_location_id"] is None and response.json()["status"] == "absent"


def test_future_correction_is_rejected_on_current_attendance_date(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
) -> None:
    record = attendance_record(scenario.employees["employee_a"], date(2026, 10, 14), hours=0)
    seeded_session.add(record)
    headers = bearer(login_token(auth_client, scenario.employees["hr"], initial_password))
    response = auth_client.patch(
        f"/api/v1/attendance/{record.id}",
        headers=headers,
        json={"clock_out": "2026-10-14T17:00:00+07:00", "reason": "Future attempt"},
    )
    assert response.status_code == 422 and response.json()["code"] == "INVALID_CLOCK_TIMES"


ENDPOINTS = [
    ("GET", "/attendance/today", None),
    ("POST", "/attendance/clock-in", {"work_mode": "remote"}),
    ("POST", "/attendance/clock-out", {"work_mode": "remote"}),
    ("GET", "/attendance/calendar", None),
    ("GET", "/attendance", None),
    ("PATCH", "/attendance/9223372036854775808", {"status": "absent", "reason": "Review"}),
    ("GET", "/team/attendance", None),
]


@pytest.mark.parametrize("method,path,payload", ENDPOINTS)
def test_every_attendance_endpoint_requires_authentication(
    auth_client: TestClient,
    method: str,
    path: str,
    payload: dict[str, Any] | None,
) -> None:
    assert auth_client.request(method, f"/api/v1{path}", json=payload).status_code == 401


@pytest.mark.parametrize("method,path,payload", ENDPOINTS)
def test_every_attendance_endpoint_enforces_password_change(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    seeded_session: Session,
    method: str,
    path: str,
    payload: dict[str, Any] | None,
) -> None:
    employee = scenario.employees["hr"]
    employee.must_change_password = True
    seeded_session.flush()
    headers = bearer(login_token(auth_client, employee, initial_password))
    response = auth_client.request(method, f"/api/v1{path}", headers=headers, json=payload)
    assert response.status_code == 403 and response.json()["code"] == "PASSWORD_CHANGE_REQUIRED"


@pytest.mark.parametrize("actor,status", [("employee_a", 403), ("manager_a", 404), ("hr", 404)])
def test_missing_attendance_edit_does_not_bypass_permission_check(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    actor: str,
    status: int,
) -> None:
    headers = bearer(login_token(auth_client, scenario.employees[actor], initial_password))
    assert (
        auth_client.patch(
            "/api/v1/attendance/9223372036854775808",
            headers=headers,
            json={"status": "absent", "reason": "Review"},
        ).status_code
        == status
    )

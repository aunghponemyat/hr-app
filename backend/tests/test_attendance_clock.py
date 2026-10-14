import logging
from datetime import timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Attendance, Permission, RolePermission, TeamWorkLocation, WorkLocation
from app.models.enums import AttendanceStatus, WorkMode
from tests.attendance_support import AttendanceClock, attendance_record
from tests.authz_support import AuthzScenario
from tests.test_auth import bearer, login_token


@pytest.fixture
def work_location(seeded_session: Session, scenario: AuthzScenario) -> WorkLocation:
    location = WorkLocation(
        name="HQ Office",
        latitude=Decimal("13.756300"),
        longitude=Decimal("100.501800"),
        allowed_radius_m=100,
    )
    seeded_session.add(location)
    seeded_session.flush()
    seeded_session.add(
        TeamWorkLocation(team_id=scenario.teams["a"].id, work_location_id=location.id)
    )
    seeded_session.flush()
    return location


@pytest.mark.parametrize("actor", ["employee_a", "senior", "manager_a", "hr", "c_level"])
def test_remote_clock_today_flow_for_every_role(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
    actor: str,
) -> None:
    employee = scenario.employees[actor]
    headers = bearer(login_token(auth_client, employee, initial_password))
    today = auth_client.get("/api/v1/attendance/today", headers=headers)
    assert today.status_code == 200 and today.json()["next_action"] == "clock_in"
    before = auth_client.post(
        "/api/v1/attendance/clock-out", headers=headers, json={"work_mode": "remote"}
    )
    assert before.status_code == 409 and before.json()["code"] == "NOT_CLOCKED_IN"
    response = auth_client.post(
        "/api/v1/attendance/clock-in",
        headers=headers,
        json={"work_mode": "remote", "latitude": 91, "longitude": 181, "accuracy_m": -1},
    )
    assert response.status_code == 200, response.text
    row = response.json()["attendance"]
    assert row["clock_in"] == "2026-10-14T09:00:00+07:00" and row["attendance_date"] == "2026-10-14"
    assert row["status"] == "present" and row["work_location_id"] is None
    assert all(value is None for value in row["clock_in_gps"].values())
    assert "Clocked in at 09:00 (Remote)" in response.json()["message"]
    assert (
        auth_client.get("/api/v1/attendance/today", headers=headers).json()["next_action"]
        == "clock_out"
    )
    duplicate = auth_client.post(
        "/api/v1/attendance/clock-in", headers=headers, json={"work_mode": "remote"}
    )
    assert duplicate.status_code == 409 and duplicate.json()["code"] == "ALREADY_CLOCKED_IN"
    attendance_clock.advance(hours=8, minutes=3)
    # The stored remote mode wins over the request's onsite choice.
    response = auth_client.post(
        "/api/v1/attendance/clock-out", headers=headers, json={"work_mode": "onsite"}
    )
    assert response.status_code == 200 and response.json()["attendance"]["status"] == "present"
    assert "Worked 8h 03m" in response.json()["message"]
    assert all(value is None for value in response.json()["attendance"]["clock_out_gps"].values())
    assert (
        auth_client.get("/api/v1/attendance/today", headers=headers).json()["next_action"] == "none"
    )
    duplicate = auth_client.post(
        "/api/v1/attendance/clock-out", headers=headers, json={"work_mode": "remote"}
    )
    assert duplicate.status_code == 409 and duplicate.json()["code"] == "ALREADY_CLOCKED_OUT"
    records = seeded_session.scalars(
        select(Attendance).where(Attendance.employee_id == employee.id)
    ).all()
    assert (
        len(records) == 1
        and records[0].clock_in is not None
        and records[0].clock_in.tzinfo == timezone.utc
    )


@pytest.mark.parametrize(
    "hours,status", [(0, "half-day"), (3.999, "half-day"), (4, "present"), (8, "present")]
)
def test_half_day_threshold_exact_boundary(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    hours: float,
    status: str,
) -> None:
    headers = bearer(login_token(auth_client, scenario.employees["employee_a"], initial_password))
    assert (
        auth_client.post(
            "/api/v1/attendance/clock-in", headers=headers, json={"work_mode": "remote"}
        ).status_code
        == 200
    )
    attendance_clock.advance(hours=hours)
    response = auth_client.post(
        "/api/v1/attendance/clock-out", headers=headers, json={"work_mode": "remote"}
    )
    assert response.status_code == 200 and response.json()["attendance"]["status"] == status


def test_onsite_clock_and_failed_clock_out_preserve_evidence(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    work_location: WorkLocation,
    seeded_session: Session,
) -> None:
    headers = bearer(login_token(auth_client, scenario.employees["employee_a"], initial_password))
    fix = {"work_mode": "onsite", "latitude": 13.7563, "longitude": 100.5018, "accuracy_m": 10.123}
    response = auth_client.post("/api/v1/attendance/clock-in", headers=headers, json=fix)
    assert response.status_code == 200, response.text
    row = response.json()["attendance"]
    assert row["work_location_id"] == work_location.id and row["work_location_name"] == "HQ Office"
    assert row["clock_in_gps"]["verified"] is True and row["clock_in_gps"]["distance_m"] == "0.00"
    assert (
        row["clock_in_gps"]["accuracy_m"] == "10.12" and "HQ Office" in response.json()["message"]
    )
    attendance_clock.advance(hours=8)
    before = seeded_session.get(Attendance, row["id"])
    assert before is not None
    failed = auth_client.post(
        "/api/v1/attendance/clock-out",
        headers=headers,
        json={**fix, "latitude": 13.7613, "work_mode": "remote"},
    )
    assert failed.status_code == 403 and failed.json()["code"] == "OUTSIDE_WORK_PERIMETER"
    seeded_session.refresh(before)
    assert (
        before.clock_out is None
        and before.clock_out_verified is None
        and before.status == AttendanceStatus.PRESENT
    )
    missing = auth_client.post(
        "/api/v1/attendance/clock-out", headers=headers, json={"work_mode": "remote"}
    )
    assert missing.status_code == 422 and missing.json()["code"] == "GPS_REQUIRED"
    response = auth_client.post(
        "/api/v1/attendance/clock-out", headers=headers, json={**fix, "work_mode": "remote"}
    )
    assert (
        response.status_code == 200 and response.json()["attendance"]["clock_out_gps"]["verified"]
    )
    assert response.json()["attendance"]["work_location_id"] == work_location.id


@pytest.mark.parametrize(
    "fix,code",
    [
        ({}, "GPS_REQUIRED"),
        ({"latitude": 13.7563}, "GPS_REQUIRED"),
        ({"latitude": 13.7563, "longitude": 100.5018}, "GPS_REQUIRED"),
        ({"latitude": 91, "longitude": 100.5018, "accuracy_m": 10}, "GPS_REQUIRED"),
        ({"latitude": 13.7563, "longitude": 100.5018, "accuracy_m": -1}, "GPS_REQUIRED"),
        ({"latitude": 13.7563, "longitude": 100.5018, "accuracy_m": 101}, "LOW_GPS_ACCURACY"),
        ({"latitude": 13.7613, "longitude": 100.5018, "accuracy_m": 10}, "OUTSIDE_WORK_PERIMETER"),
    ],
)
def test_failed_gps_does_not_create_row_and_warning_omits_coordinates(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    work_location: WorkLocation,
    seeded_session: Session,
    caplog: pytest.LogCaptureFixture,
    fix: dict[str, float],
    code: str,
) -> None:
    headers = bearer(login_token(auth_client, scenario.employees["employee_a"], initial_password))
    with caplog.at_level(logging.WARNING, logger="app.services.attendance_service"):
        response = auth_client.post(
            "/api/v1/attendance/clock-in", headers=headers, json={"work_mode": "onsite", **fix}
        )
    assert response.json()["code"] == code and response.status_code == (
        403 if code == "OUTSIDE_WORK_PERIMETER" else 422
    )
    assert not seeded_session.scalars(select(Attendance)).all()
    assert code in caplog.text and "13.7563" not in caplog.text and "100.5018" not in caplog.text
    assert work_location.name not in caplog.text


@pytest.mark.parametrize("actor", ["employee_b", "unassigned"])
def test_team_specific_or_missing_work_location(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    work_location: WorkLocation,
    actor: str,
) -> None:
    headers = bearer(login_token(auth_client, scenario.employees[actor], initial_password))
    response = auth_client.post(
        "/api/v1/attendance/clock-in",
        headers=headers,
        json={"work_mode": "onsite", "latitude": 13.7563, "longitude": 100.5018, "accuracy_m": 10},
    )
    assert response.status_code == 422 and response.json()["code"] == "NO_WORK_LOCATION_CONFIGURED"


@pytest.mark.parametrize(
    "extra",
    [
        {"timestamp": "2000-01-01T00:00:00Z"},
        {"clock_in": "2000-01-01T00:00:00Z"},
        {"verified": True},
        {"employee_id": 1},
    ],
)
def test_client_time_verification_and_target_are_rejected(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
    extra: dict[str, Any],
) -> None:
    headers = bearer(login_token(auth_client, scenario.employees["employee_a"], initial_password))
    for path in ["clock-in", "clock-out"]:
        response = auth_client.post(
            f"/api/v1/attendance/{path}", headers=headers, json={"work_mode": "remote", **extra}
        )
        assert response.status_code == 422
    assert not seeded_session.scalars(select(Attendance)).all()


def test_overnight_clock_out_leaves_previous_row_open_and_allows_new_day(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
) -> None:
    employee = scenario.employees["employee_a"]
    previous = attendance_record(employee, attendance_clock.value.date() - timedelta(days=1))
    previous.clock_out = None
    seeded_session.add(previous)
    headers = bearer(login_token(auth_client, employee, initial_password))
    response = auth_client.post(
        "/api/v1/attendance/clock-out", headers=headers, json={"work_mode": "remote"}
    )
    assert response.status_code == 409 and response.json()["code"] == "NOT_CLOCKED_IN"
    seeded_session.refresh(previous)
    assert previous.clock_out is None
    assert (
        auth_client.post(
            "/api/v1/attendance/clock-in", headers=headers, json={"work_mode": "remote"}
        ).status_code
        == 200
    )


def test_clock_in_uses_server_office_date_and_revoked_permission(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
) -> None:
    employee = scenario.employees["employee_a"]
    headers = bearer(login_token(auth_client, employee, initial_password))
    attendance_clock.value = attendance_clock.value.replace(hour=18)
    response = auth_client.post(
        "/api/v1/attendance/clock-in", headers=headers, json={"work_mode": "remote"}
    )
    assert response.json()["attendance"]["attendance_date"] == "2026-10-15"
    permission_id = seeded_session.scalar(
        select(Permission.id).where(Permission.code == "attendance.create.self")
    )
    seeded_session.query(RolePermission).filter(
        RolePermission.role_id == employee.role_id, RolePermission.permission_id == permission_id
    ).delete()
    seeded_session.commit()
    response = auth_client.post(
        "/api/v1/attendance/clock-out", headers=headers, json={"work_mode": "remote"}
    )
    assert response.status_code == 403 and response.json()["code"] == "PERMISSION_DENIED"


def test_clock_in_updates_an_existing_unclocked_row_only_after_verification(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
    work_location: WorkLocation,
) -> None:
    employee = scenario.employees["employee_a"]
    row = Attendance(
        employee_id=employee.id,
        attendance_date=attendance_clock.value.date(),
        work_mode=WorkMode.ONSITE,
        work_location_id=work_location.id,
        status=AttendanceStatus.ABSENT,
        clock_in_verified=True,
        clock_in_latitude=Decimal("13.000000"),
    )
    seeded_session.add(row)
    headers = bearer(login_token(auth_client, employee, initial_password))
    failed = auth_client.post(
        "/api/v1/attendance/clock-in",
        headers=headers,
        json={"work_mode": "onsite", "latitude": 13.7613, "longitude": 100.5018, "accuracy_m": 10},
    )
    assert failed.status_code == 403
    seeded_session.refresh(row)
    assert row.clock_in is None and row.status == AttendanceStatus.ABSENT
    assert row.clock_in_verified and row.clock_in_latitude == Decimal("13.000000")
    response = auth_client.post(
        "/api/v1/attendance/clock-in", headers=headers, json={"work_mode": "remote"}
    )
    assert response.status_code == 200 and response.json()["attendance"]["id"] == row.id
    assert response.json()["attendance"]["status"] == "present"
    assert response.json()["attendance"]["work_location_id"] is None
    assert all(value is None for value in response.json()["attendance"]["clock_in_gps"].values())

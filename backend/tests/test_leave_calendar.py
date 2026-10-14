from datetime import date

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.models.enums import HalfDayPeriod, LeaveStatus
from tests.attendance_support import AttendanceClock, attendance_record
from tests.authz_support import AuthzScenario
from tests.leave_support import leave_payload, leave_record
from tests.test_auth import bearer, login_token


@pytest.mark.parametrize(
    "status,display",
    [
        (LeaveStatus.PENDING, None),
        (LeaveStatus.APPROVED, "leave"),
        (LeaveStatus.REJECTED, None),
        (LeaveStatus.CANCELLED, None),
    ],
)
def test_only_approved_leave_affects_today_calendar_table_and_roster(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
    status: LeaveStatus,
    display: str | None,
) -> None:
    employee = scenario.employees["employee_a"]
    row = leave_record(seeded_session, employee, scenario.employees["manager_a"], status=status)
    seeded_session.add(row)
    headers = bearer(login_token(auth_client, employee, initial_password))
    params = {"from": "2026-10-14", "to": "2026-10-14"}
    calendar = auth_client.get("/api/v1/attendance/calendar", headers=headers, params=params).json()
    assert calendar["entries"][0]["display_status"] == display
    assert calendar["summary"]["leave_days"] == (1 if status == LeaveStatus.APPROVED else 0)
    table = auth_client.get("/api/v1/attendance", headers=headers, params=params).json()
    assert table["items"][0]["display_status"] == display
    assert len(table["items"][0]["leaves"]) == (1 if status == LeaveStatus.APPROVED else 0)
    manager_headers = bearer(
        login_token(auth_client, scenario.employees["manager_a"], initial_password)
    )
    roster = auth_client.get("/api/v1/team/members", headers=manager_headers).json()
    statuses = {item["id"]: item["today_status"] for item in roster["items"]}
    assert statuses[employee.id] == display
    team = auth_client.get("/api/v1/team/attendance", headers=manager_headers, params=params).json()
    summary = next(
        item["summary"] for item in team["items"] if item["employee"]["id"] == employee.id
    )
    assert summary["leave_days"] == calendar["summary"]["leave_days"]


@pytest.mark.parametrize("both", [False, True])
def test_half_day_overlay_preserves_attendance_and_both_requests(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
    both: bool,
) -> None:
    employee, manager = scenario.employees["employee_a"], scenario.employees["manager_a"]
    record = attendance_record(employee, date(2026, 10, 13), hours=4)
    seeded_session.add(record)
    seeded_session.add(
        leave_record(
            seeded_session,
            employee,
            manager,
            day=date(2026, 10, 13),
            half=HalfDayPeriod.MORNING,
            status=LeaveStatus.APPROVED,
        )
    )
    if both:
        seeded_session.add(
            leave_record(
                seeded_session,
                employee,
                manager,
                day=date(2026, 10, 13),
                half=HalfDayPeriod.AFTERNOON,
                status=LeaveStatus.APPROVED,
            )
        )
    headers = bearer(login_token(auth_client, employee, initial_password))
    response = auth_client.get(
        "/api/v1/attendance/calendar",
        headers=headers,
        params={"from": "2026-10-13", "to": "2026-10-13"},
    )
    assert response.status_code == 200
    entry = response.json()["entries"][0]
    assert entry["display_status"] == ("leave" if both else "half-day")
    assert (
        len(entry["leaves"]) == (2 if both else 1)
        and entry["leave"]["half_day_period"] == "morning"
    )
    assert entry["worked_hours"] == 4 and entry["clock_in"] is not None
    seeded_session.refresh(record)
    assert record.status.value == "present"


def test_full_leave_skips_weekends_and_overrides_future_upcoming(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
) -> None:
    seeded_session.add(
        leave_record(
            seeded_session,
            scenario.employees["employee_a"],
            scenario.employees["manager_a"],
            day=date(2026, 10, 16),
            end=date(2026, 10, 19),
            status=LeaveStatus.APPROVED,
        )
    )
    headers = bearer(login_token(auth_client, scenario.employees["employee_a"], initial_password))
    response = auth_client.get(
        "/api/v1/attendance/calendar",
        headers=headers,
        params={"from": "2026-10-16", "to": "2026-10-19"},
    )
    entries = response.json()["entries"]
    assert [item["display_status"] for item in entries] == [
        "leave",
        "upcoming",
        "upcoming",
        "leave",
    ]
    assert entries[1]["leave"] is None and response.json()["summary"]["leave_days"] == 2


def test_visible_approved_leave_adds_years_even_without_attendance(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
) -> None:
    employee, manager = scenario.employees["employee_a"], scenario.employees["manager_a"]
    seeded_session.add(
        leave_record(
            seeded_session,
            employee,
            manager,
            day=date(2026, 12, 31),
            end=date(2027, 1, 1),
            status=LeaveStatus.APPROVED,
        )
    )
    seeded_session.add(
        leave_record(
            seeded_session, employee, manager, day=date(2024, 1, 1), status=LeaveStatus.APPROVED
        )
    )
    seeded_session.add(
        leave_record(
            seeded_session, employee, manager, day=date(2028, 1, 3), status=LeaveStatus.PENDING
        )
    )
    headers = bearer(login_token(auth_client, employee, initial_password))
    assert auth_client.get("/api/v1/attendance/calendar", headers=headers).json()[
        "available_years"
    ] == [2027, 2026]
    admin_headers = bearer(login_token(auth_client, scenario.employees["hr"], initial_password))
    assert auth_client.get(
        "/api/v1/attendance/calendar", headers=admin_headers, params={"employee_id": employee.id}
    ).json()["available_years"] == [2027, 2026, 2024]


def test_request_approve_then_future_cancel_removes_calendar_overlay(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
) -> None:
    employee_headers = bearer(
        login_token(auth_client, scenario.employees["employee_a"], initial_password)
    )
    created = auth_client.post(
        "/api/v1/leave-requests",
        headers=employee_headers,
        json=leave_payload(seeded_session, scenario.employees["manager_a"], num_days=1),
    )
    assert created.status_code == 201
    request_id = created.json()["id"]
    manager_headers = bearer(
        login_token(auth_client, scenario.employees["manager_a"], initial_password)
    )
    assert (
        auth_client.post(
            f"/api/v1/leave-requests/{request_id}/approve", headers=manager_headers
        ).status_code
        == 200
    )
    params = {"from": "2026-10-16", "to": "2026-10-16"}
    assert (
        auth_client.get(
            "/api/v1/attendance/calendar", headers=employee_headers, params=params
        ).json()["entries"][0]["display_status"]
        == "leave"
    )
    assert (
        auth_client.post(
            f"/api/v1/leave-requests/{request_id}/cancel", headers=employee_headers
        ).status_code
        == 200
    )
    assert (
        auth_client.get(
            "/api/v1/attendance/calendar", headers=employee_headers, params=params
        ).json()["entries"][0]["display_status"]
        == "upcoming"
    )

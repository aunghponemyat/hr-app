import codecs
import csv
from datetime import date
from decimal import Decimal
from io import StringIO
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.models import WorkLocation
from app.models.enums import HalfDayPeriod, LeaveStatus, WorkMode
from tests.attendance_support import AttendanceClock, attendance_record
from tests.authz_support import AuthzScenario
from tests.leave_support import leave_record
from tests.test_auth import bearer, login_token
from tests.test_report_csv import ATTENDANCE_COLUMNS, LEAVE_COLUMNS

EXPORT_PATHS = ["/attendance/export", "/admin/reports/attendance.csv", "/admin/reports/leave.csv"]


def csv_rows(response: httpx.Response, columns: list[str]) -> list[dict[str, str]]:
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-disposition"].startswith("attachment; filename=")
    assert response.content.startswith(codecs.BOM_UTF8)
    reader = csv.DictReader(StringIO(response.content.decode("utf-8-sig"), newline=""))
    assert reader.fieldnames == columns
    return list(reader)


@pytest.mark.parametrize("actor", ["employee_a", "senior", "manager_a", "hr", "c_level"])
def test_self_export_is_self_only_for_every_role(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
    actor: str,
) -> None:
    for employee in scenario.employees.values():
        seeded_session.add(attendance_record(employee, date(2026, 10, 13)))
    caller = scenario.employees[actor]
    headers = bearer(login_token(auth_client, caller, initial_password))
    response = auth_client.get(
        "/api/v1/attendance/export",
        headers=headers,
        params={"from": "2026-10-13", "to": "2026-10-14"},
    )
    rows = csv_rows(response, ATTENDANCE_COLUMNS)
    assert len(rows) == 2 and {row["employee_id"] for row in rows} == {caller.employee_id}
    assert rows[0]["display_status"] == "present" and rows[0]["work_mode"] == "remote"
    assert (
        rows[0]["clock_in_local"] == "2026-10-13T09:00:00+07:00"
        and rows[0]["worked_hours"] == "8.00"
    )
    assert (
        rows[1]["display_status"] == ""
        and rows[1]["clock_in_verified"] == ""
        and rows[1]["clock_out_distance_m"] == ""
    )
    assert (
        response.headers["content-disposition"]
        == f"attachment; filename=attendance_{caller.employee_id}_2026-10-13_2026-10-14.csv"
    )
    for extra in [
        {"employee_id": scenario.employees["employee_b"].id},
        {"team_id": scenario.teams["b"].id},
    ]:
        assert (
            auth_client.get(
                "/api/v1/attendance/export",
                headers=headers,
                params={"from": "2026-10-13", "to": "2026-10-14", **extra},
            ).status_code
            == 422
        )


@pytest.mark.parametrize("actor", ["employee_a", "senior", "manager_a", "hr", "c_level"])
@pytest.mark.parametrize("kind", ["attendance", "leave"])
def test_admin_export_role_matrix(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
    actor: str,
    kind: str,
) -> None:
    seeded_session.add(
        leave_record(
            seeded_session, scenario.employees["employee_a"], scenario.employees["manager_a"]
        )
    )
    headers = bearer(login_token(auth_client, scenario.employees[actor], initial_password))
    response = auth_client.get(
        f"/api/v1/admin/reports/{kind}.csv",
        headers=headers,
        params={"from": "2026-10-14", "to": "2026-10-14"},
    )
    if actor not in {"hr", "c_level"}:
        assert response.status_code == 403 and response.json()["code"] == "PERMISSION_DENIED"
    else:
        rows = csv_rows(response, ATTENDANCE_COLUMNS if kind == "attendance" else LEAVE_COLUMNS)
        if kind == "attendance":
            assert {row["employee_id"] for row in rows} == {
                employee.employee_id for employee in scenario.employees.values()
            }
        else:
            assert (
                len(rows) == 1
                and rows[0]["employee_id"] == scenario.employees["employee_a"].employee_id
            )


@pytest.mark.parametrize("kind", ["attendance", "leave"])
def test_admin_filters_current_membership_inactive_employees_and_empty_report(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
    kind: str,
) -> None:
    for key in ["employee_a", "employee_b", "senior"]:
        seeded_session.add(
            leave_record(
                seeded_session,
                scenario.employees[key],
                scenario.employees["manager_b"]
                if key == "employee_b"
                else scenario.employees["manager_a"],
            )
        )
    scenario.employees["senior"].is_active = False
    scenario.employees["employee_a"].team_id = scenario.teams["b"].id
    headers = bearer(login_token(auth_client, scenario.employees["hr"], initial_password))
    path = f"/api/v1/admin/reports/{kind}.csv"
    params: dict[str, Any] = {
        "from": "2026-10-14",
        "to": "2026-10-14",
        "team_id": scenario.teams["a"].id,
    }
    rows = csv_rows(
        auth_client.get(path, headers=headers, params=params),
        ATTENDANCE_COLUMNS if kind == "attendance" else LEAVE_COLUMNS,
    )
    expected = scenario.team_ids("a") if kind == "attendance" else {scenario.employees["senior"].id}
    assert {row["employee_id"] for row in rows} == {
        employee.employee_id for employee in scenario.employees.values() if employee.id in expected
    }
    assert scenario.employees["senior"].employee_id in {row["employee_id"] for row in rows}
    filtered = auth_client.get(
        path, headers=headers, params={**params, "employee_id": scenario.employees["senior"].id}
    )
    assert (
        len(csv_rows(filtered, ATTENDANCE_COLUMNS if kind == "attendance" else LEAVE_COLUMNS)) == 1
    )
    mismatch = auth_client.get(
        path, headers=headers, params={**params, "employee_id": scenario.employees["employee_b"].id}
    )
    assert csv_rows(mismatch, ATTENDANCE_COLUMNS if kind == "attendance" else LEAVE_COLUMNS) == []


def test_leave_export_all_statuses_overlap_full_request_and_decision_fields(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
) -> None:
    employee, manager = scenario.employees["employee_a"], scenario.employees["manager_a"]
    for status in LeaveStatus:
        request = leave_record(
            seeded_session,
            employee,
            manager,
            day=date(2026, 10, 12),
            end=date(2026, 10, 15),
            status=status,
        )
        request.num_days = Decimal("4")
        request.reason_text = 'Medical detail, "quoted"\nSecond line ไทย'
        request.remark = "Remark"
        if status == LeaveStatus.APPROVED:
            request.decided_by = manager.id
            request.decided_at = attendance_clock.now()
        seeded_session.add(request)
    seeded_session.add(
        leave_record(
            seeded_session, employee, manager, day=date(2026, 10, 16), half=HalfDayPeriod.AFTERNOON
        )
    )
    seeded_session.add(leave_record(seeded_session, employee, manager, day=date(2026, 10, 9)))
    headers = bearer(login_token(auth_client, scenario.employees["hr"], initial_password))
    response = auth_client.get(
        "/api/v1/admin/reports/leave.csv",
        headers=headers,
        params={"from": "2026-10-14", "to": "2026-10-16"},
    )
    rows = csv_rows(response, LEAVE_COLUMNS)
    assert len(rows) == 5 and {row["status"] for row in rows} == {
        status.value for status in LeaveStatus
    }
    assert (
        rows[0]["start_date"] == "2026-10-12"
        and rows[0]["end_date"] == "2026-10-15"
        and rows[0]["num_days"] == "4.0"
    )
    assert rows[0]["reason_text"] == 'Medical detail, "quoted"\nSecond line ไทย'
    approved = next(row for row in rows if row["status"] == "approved")
    assert approved["decided_by"] == f"{manager.first_name} {manager.last_name}"
    assert approved["decided_at"] == "2026-10-14T09:00:00+07:00"
    assert rows[-1]["duration"] == "half_day (afternoon)" and rows[-1]["num_days"] == "0.5"
    assert rows[-1]["decided_by"] == "" and rows[-1]["decided_at"] == ""
    assert "password_hash" not in response.text and "refresh_token" not in response.text


def test_attendance_export_derived_statuses_leave_and_gps_precision(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
) -> None:
    employee, manager = scenario.employees["employee_a"], scenario.employees["manager_a"]
    location = WorkLocation(
        name="HQ Office",
        latitude=Decimal("13.756300"),
        longitude=Decimal("100.501800"),
        allowed_radius_m=100,
    )
    seeded_session.add(location)
    seeded_session.flush()
    row = attendance_record(employee, date(2026, 10, 12), mode=WorkMode.ONSITE)
    row.work_location_id = location.id
    row.clock_in_verified, row.clock_out_verified = True, False
    row.clock_in_distance_m, row.clock_out_distance_m = Decimal("12.30"), Decimal("40.00")
    seeded_session.add(row)
    seeded_session.add(
        leave_record(
            seeded_session,
            employee,
            manager,
            day=date(2026, 10, 13),
            status=LeaveStatus.APPROVED,
            half=HalfDayPeriod.MORNING,
        )
    )
    seeded_session.add(
        leave_record(
            seeded_session, employee, manager, day=date(2026, 10, 16), status=LeaveStatus.APPROVED
        )
    )
    headers = bearer(login_token(auth_client, employee, initial_password))
    response = auth_client.get(
        "/api/v1/attendance/export",
        headers=headers,
        params={"from": "2026-10-09", "to": "2026-10-17"},
    )
    rows = {row["date"]: row for row in csv_rows(response, ATTENDANCE_COLUMNS)}
    assert (
        rows["2026-10-09"]["display_status"] == "absent"
        and rows["2026-10-10"]["display_status"] == "weekend"
    )
    assert (
        rows["2026-10-12"]["work_location"] == "HQ Office"
        and rows["2026-10-12"]["clock_in_verified"] == "true"
    )
    assert (
        rows["2026-10-12"]["clock_out_verified"] == "false"
        and rows["2026-10-12"]["clock_in_distance_m"] == "12.30"
    )
    assert (
        rows["2026-10-13"]["display_status"] == "half-day"
        and rows["2026-10-16"]["display_status"] == "leave"
    )
    assert (
        rows["2026-10-17"]["display_status"] == "upcoming"
        and rows["2026-10-14"]["display_status"] == ""
    )


@pytest.mark.parametrize("path", EXPORT_PATHS)
def test_export_requires_authentication(auth_client: TestClient, path: str) -> None:
    assert (
        auth_client.get(
            f"/api/v1{path}", params={"from": "2026-10-13", "to": "2026-10-14"}
        ).status_code
        == 401
    )


@pytest.mark.parametrize("path", EXPORT_PATHS)
def test_export_requires_completed_password_change(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    seeded_session: Session,
    path: str,
) -> None:
    employee = scenario.employees["hr"]
    employee.must_change_password = True
    seeded_session.flush()
    headers = bearer(login_token(auth_client, employee, initial_password))
    response = auth_client.get(
        f"/api/v1{path}", headers=headers, params={"from": "2026-10-13", "to": "2026-10-14"}
    )
    assert response.status_code == 403 and response.json()["code"] == "PASSWORD_CHANGE_REQUIRED"

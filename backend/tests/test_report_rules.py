from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Permission, Role, RolePermission
from tests.attendance_support import AttendanceClock
from tests.authz_support import AuthzScenario
from tests.leave_support import leave_record
from tests.test_auth import bearer, login_token
from tests.test_report_api import EXPORT_PATHS, csv_rows
from tests.test_report_csv import ATTENDANCE_COLUMNS, LEAVE_COLUMNS


@pytest.mark.parametrize("path", EXPORT_PATHS)
@pytest.mark.parametrize(
    "params,code",
    [
        ({"from": "2025-01-01", "to": "2026-01-02"}, "RANGE_TOO_LARGE"),
        ({"from": "2026-10-14", "to": "2026-10-13"}, "INVALID_RANGE"),
        ({"from": "2026-10-01"}, "VALIDATION_ERROR"),
        ({"to": "2026-10-01"}, "VALIDATION_ERROR"),
        ({"from": "invalid", "to": "2026-10-01"}, "VALIDATION_ERROR"),
        ({"from": "2026-10-01", "to": "2026-10-02", "page_size": 2}, "VALIDATION_ERROR"),
    ],
)
def test_export_range_validation_precedes_csv_response(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    path: str,
    params: dict[str, Any],
    code: str,
) -> None:
    headers = bearer(login_token(auth_client, scenario.employees["hr"], initial_password))
    response = auth_client.get(f"/api/v1{path}", headers=headers, params=params)
    assert response.status_code == 422 and response.json()["code"] == code, response.text
    assert response.headers["content-type"] == "application/json"
    assert "content-disposition" not in response.headers


@pytest.mark.parametrize(
    "actor,unrestricted",
    [("employee_a", False), ("manager_a", False), ("hr", True), ("c_level", True)],
)
def test_self_history_policy_effective_filename_and_inclusive_cap(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    actor: str,
    unrestricted: bool,
) -> None:
    employee = scenario.employees[actor]
    headers = bearer(login_token(auth_client, employee, initial_password))
    response = auth_client.get(
        "/api/v1/attendance/export",
        headers=headers,
        params={"from": "2025-10-01", "to": "2025-10-15"},
    )
    rows = csv_rows(response, ATTENDANCE_COLUMNS)
    assert rows[0]["date"] == ("2025-10-01" if unrestricted else "2025-10-14")
    assert f"_{rows[0]['date']}_2025-10-15.csv" in response.headers["content-disposition"]
    old = auth_client.get(
        "/api/v1/attendance/export",
        headers=headers,
        params={"from": "2024-01-01", "to": "2024-01-02"},
    )
    assert old.status_code == (200 if unrestricted else 422)
    if not unrestricted:
        assert old.json()["code"] == "HISTORY_LIMIT"
    exact = auth_client.get(
        "/api/v1/attendance/export",
        headers=headers,
        params={"from": "2025-10-14", "to": "2026-10-14"},
    )
    assert len(csv_rows(exact, ATTENDANCE_COLUMNS)) == 366
    too_long = auth_client.get(
        "/api/v1/attendance/export",
        headers=headers,
        params={"from": "2025-10-13", "to": "2026-10-14"},
    )
    assert too_long.status_code == 422 and too_long.json()["code"] == "RANGE_TOO_LARGE"


@pytest.mark.parametrize("kind", ["attendance", "leave"])
def test_admin_default_month_and_historical_ranges(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
    kind: str,
) -> None:
    seeded_session.add(
        leave_record(
            seeded_session,
            scenario.employees["employee_a"],
            scenario.employees["manager_a"],
            day=date(2020, 1, 1),
        )
    )
    headers = bearer(login_token(auth_client, scenario.employees["hr"], initial_password))
    path = f"/api/v1/admin/reports/{kind}.csv"
    response = auth_client.get(path, headers=headers)
    rows = csv_rows(response, ATTENDANCE_COLUMNS if kind == "attendance" else LEAVE_COLUMNS)
    assert (
        response.headers["content-disposition"]
        == f"attachment; filename={kind}_all_2026-10-01_2026-10-31.csv"
    )
    assert len(rows) == (31 * len(scenario.ids()) if kind == "attendance" else 0)
    old = auth_client.get(path, headers=headers, params={"from": "2020-01-01", "to": "2020-01-01"})
    old_rows = csv_rows(old, ATTENDANCE_COLUMNS if kind == "attendance" else LEAVE_COLUMNS)
    assert len(old_rows) == (len(scenario.ids()) if kind == "attendance" else 1)


@pytest.mark.parametrize("kind", ["attendance", "leave"])
@pytest.mark.parametrize("field", ["team_id", "employee_id"])
def test_missing_admin_filters_return_json_404_after_authorization(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    kind: str,
    field: str,
) -> None:
    params = {"from": "2026-10-14", "to": "2026-10-14", field: 2**63}
    headers = bearer(login_token(auth_client, scenario.employees["hr"], initial_password))
    response = auth_client.get(f"/api/v1/admin/reports/{kind}.csv", headers=headers, params=params)
    assert response.status_code == 404 and response.json()["code"] == "NOT_FOUND"
    denied_headers = bearer(
        login_token(auth_client, scenario.employees["manager_a"], initial_password)
    )
    assert (
        auth_client.get(
            f"/api/v1/admin/reports/{kind}.csv", headers=denied_headers, params=params
        ).status_code
        == 403
    )


def test_export_permission_is_sufficient_without_other_read_permissions(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
) -> None:
    employee = scenario.employees["employee_a"]
    employee_headers = bearer(login_token(auth_client, employee, initial_password))
    admin = scenario.employees["hr"]
    admin_headers = bearer(login_token(auth_client, admin, initial_password))
    read_permissions = select(Permission.id).where(Permission.action == "read")
    seeded_session.execute(
        delete(RolePermission).where(
            RolePermission.role_id.in_([employee.role_id, admin.role_id]),
            RolePermission.permission_id.in_(read_permissions),
        )
    )
    seeded_session.commit()
    assert (
        auth_client.get("/api/v1/attendance/calendar", headers=employee_headers).status_code == 403
    )
    assert auth_client.get("/api/v1/admin/employees", headers=admin_headers).status_code == 403
    params = {"from": "2026-10-14", "to": "2026-10-14"}
    assert (
        len(
            csv_rows(
                auth_client.get(
                    "/api/v1/attendance/export", headers=employee_headers, params=params
                ),
                ATTENDANCE_COLUMNS,
            )
        )
        == 1
    )
    assert (
        csv_rows(
            auth_client.get(
                "/api/v1/admin/reports/leave.csv", headers=admin_headers, params=params
            ),
            LEAVE_COLUMNS,
        )
        == []
    )
    assert len(
        csv_rows(
            auth_client.get(
                "/api/v1/admin/reports/attendance.csv", headers=admin_headers, params=params
            ),
            ATTENDANCE_COLUMNS,
        )
    ) == len(scenario.ids())


@pytest.mark.parametrize(
    "actor,code,path",
    [
        ("employee_a", "report.export.self", "/attendance/export"),
        ("hr", "report.export.any", "/admin/reports/attendance.csv"),
        ("hr", "report.export.any", "/admin/reports/leave.csv"),
    ],
)
def test_export_grant_revocation_affects_existing_token(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
    actor: str,
    code: str,
    path: str,
) -> None:
    employee = scenario.employees[actor]
    headers = bearer(login_token(auth_client, employee, initial_password))
    permission_id = seeded_session.scalar(select(Permission.id).where(Permission.code == code))
    seeded_session.execute(
        delete(RolePermission).where(
            RolePermission.role_id == employee.role_id,
            RolePermission.permission_id == permission_id,
        )
    )
    seeded_session.commit()
    response = auth_client.get(
        f"/api/v1{path}", headers=headers, params={"from": "2026-10-14", "to": "2026-10-14"}
    )
    assert response.status_code == 403 and response.json()["code"] == "PERMISSION_DENIED"


def test_role_label_does_not_authorize_or_block_export(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
) -> None:
    admin = scenario.employees["hr"]
    headers = bearer(login_token(auth_client, admin, initial_password))
    role = seeded_session.get(Role, admin.role_id)
    assert role is not None
    role.name = "renamed_admin_label"
    seeded_session.commit()
    response = auth_client.get(
        "/api/v1/admin/reports/attendance.csv",
        headers=headers,
        params={"from": "2026-10-14", "to": "2026-10-14"},
    )
    assert len(csv_rows(response, ATTENDANCE_COLUMNS)) == len(scenario.ids())

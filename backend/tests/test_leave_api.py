from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog
from app.models.enums import LeaveStatus
from tests.attendance_support import AttendanceClock
from tests.authz_support import AuthzScenario
from tests.leave_support import leave_payload, leave_record
from tests.test_auth import bearer, login_token


@pytest.mark.parametrize("actor", ["employee_a", "senior", "manager_a", "hr", "c_level"])
def test_leave_options_and_creation_for_every_role(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
    actor: str,
) -> None:
    employee = scenario.employees[actor]
    headers = bearer(login_token(auth_client, employee, initial_password))
    options = auth_client.get("/api/v1/leave/options", headers=headers)
    assert options.status_code == 200
    data = options.json()
    assert len(data["types"]) == 7 and len(data["reasons"]) == 6
    assert data["today"] == "2026-10-14" and data["working_weekdays"] == [0, 1, 2, 3, 4]
    assert data["max_days_per_request"] == 30 and data["backdate_days"] == 7
    assert all(manager["id"] != employee.id for manager in data["managers"])
    manager = seeded_session.get(type(employee), data["managers"][0]["id"])
    assert manager is not None
    response = auth_client.post(
        "/api/v1/leave-requests", headers=headers, json=leave_payload(seeded_session, manager)
    )
    assert response.status_code == 201, response.text
    row = response.json()
    assert row["employee"]["id"] == employee.id and row["status"] == "pending"
    assert row["end_date"] == "2026-10-19" and row["num_days"] == "2.0"
    assert row["created_at"].endswith("+07:00")
    assert (
        auth_client.get(f"/api/v1/leave-requests/{row['id']}", headers=headers).status_code == 200
    )
    listed = auth_client.get("/api/v1/leave-requests", headers=headers)
    assert listed.status_code == 200 and listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == row["id"]


@pytest.mark.parametrize("actor", ["employee_a", "senior", "manager_a", "hr", "c_level"])
@pytest.mark.parametrize("target", ["employee_a", "employee_b"])
def test_request_detail_scope_and_personal_team_lists(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
    actor: str,
    target: str,
) -> None:
    row = leave_record(
        seeded_session,
        scenario.employees[target],
        scenario.employees["manager_a" if target == "employee_a" else "manager_b"],
    )
    seeded_session.add(row)
    headers = bearer(login_token(auth_client, scenario.employees[actor], initial_password))
    own = scenario.employees[actor].id == row.employee_id
    allowed = own or actor in {"hr", "c_level"} or (actor == "manager_a" and target == "employee_a")
    response = auth_client.get(f"/api/v1/leave-requests/{row.id}", headers=headers)
    assert response.status_code == (200 if allowed else 403), response.text
    personal = auth_client.get("/api/v1/leave-requests", headers=headers)
    assert personal.json()["total"] == (1 if own else 0)
    team = auth_client.get("/api/v1/leave-requests/team", headers=headers)
    if actor in {"employee_a", "senior"}:
        assert team.status_code == 403
    else:
        assert team.status_code == 200 and team.json()["total"] == (1 if allowed else 0)


@pytest.mark.parametrize("decision", ["approve", "reject"])
@pytest.mark.parametrize(
    "actor", ["employee_a", "senior", "manager_a", "manager_b", "hr", "c_level"]
)
def test_decision_permission_matrix_and_audit(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
    decision: str,
    actor: str,
) -> None:
    row = leave_record(
        seeded_session, scenario.employees["employee_a"], scenario.employees["manager_a"]
    )
    seeded_session.add(row)
    headers = bearer(login_token(auth_client, scenario.employees[actor], initial_password))
    response = auth_client.post(
        f"/api/v1/leave-requests/{row.id}/{decision}",
        headers=headers,
        json={"decision_note": "Reviewed"},
    )
    allowed = actor in {"manager_a", "hr", "c_level"}
    assert response.status_code == (200 if allowed else 403), response.text
    seeded_session.refresh(row)
    if allowed:
        assert row.status == (
            LeaveStatus.APPROVED if decision == "approve" else LeaveStatus.REJECTED
        )
        assert response.json()["decided_by"]["id"] == scenario.employees[actor].id
        assert response.json()["decided_at"] == "2026-10-14T09:00:00+07:00"
        log = seeded_session.scalars(
            select(AuditLog).where(AuditLog.entity == "leave_request")
        ).one()
        assert (
            log.action == f"leave.{decision}"
            and log.before_json is not None
            and log.before_json["status"] == "pending"
        )
        assert log.after_json is not None and log.after_json["decision_note"] == "Reviewed"
    else:
        assert row.status == LeaveStatus.PENDING and row.decided_at is None


@pytest.mark.parametrize(
    "status", [LeaveStatus.APPROVED, LeaveStatus.REJECTED, LeaveStatus.CANCELLED]
)
def test_only_pending_requests_can_be_decided(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
    status: LeaveStatus,
) -> None:
    row = leave_record(
        seeded_session,
        scenario.employees["employee_a"],
        scenario.employees["manager_a"],
        status=status,
    )
    seeded_session.add(row)
    headers = bearer(login_token(auth_client, scenario.employees["hr"], initial_password))
    for decision in ["approve", "reject"]:
        response = auth_client.post(f"/api/v1/leave-requests/{row.id}/{decision}", headers=headers)
        assert response.status_code == 409 and response.json()["code"] == "INVALID_STATE"


@pytest.mark.parametrize("actor", ["manager_a", "hr", "c_level"])
def test_nobody_can_decide_their_own_request(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
    actor: str,
) -> None:
    employee = scenario.employees[actor]
    manager = scenario.employees["c_level"] if actor != "c_level" else scenario.employees["hr"]
    row = leave_record(seeded_session, employee, manager)
    seeded_session.add(row)
    headers = bearer(login_token(auth_client, employee, initial_password))
    for decision in ["approve", "reject"]:
        response = auth_client.post(f"/api/v1/leave-requests/{row.id}/{decision}", headers=headers)
        assert response.status_code == 403 and response.json()["code"] == "SELF_APPROVAL_FORBIDDEN"


@pytest.mark.parametrize("actor,expected", [("employee_a", 403), ("manager_a", 404), ("hr", 404)])
def test_missing_request_policy(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    actor: str,
    expected: int,
) -> None:
    headers = bearer(login_token(auth_client, scenario.employees[actor], initial_password))
    assert (
        auth_client.get("/api/v1/leave-requests/9223372036854775808", headers=headers).status_code
        == expected
    )


def test_team_filters_pagination_and_out_of_scope_employee(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
) -> None:
    for day, status in [
        (date(2026, 10, 12), LeaveStatus.PENDING),
        (date(2026, 10, 13), LeaveStatus.REJECTED),
        (date(2026, 10, 14), LeaveStatus.PENDING),
    ]:
        seeded_session.add(
            leave_record(
                seeded_session,
                scenario.employees["employee_a"],
                scenario.employees["manager_a"],
                day=day,
                status=status,
            )
        )
    seeded_session.add(
        leave_record(
            seeded_session, scenario.employees["employee_b"], scenario.employees["manager_b"]
        )
    )
    headers = bearer(login_token(auth_client, scenario.employees["manager_a"], initial_password))
    params = {
        "status": "pending",
        "page_size": 1,
        "employee_id": scenario.employees["employee_a"].id,
    }
    first = auth_client.get("/api/v1/leave-requests/team", headers=headers, params=params)
    second = auth_client.get(
        "/api/v1/leave-requests/team", headers=headers, params={**params, "page": 2}
    )
    assert first.status_code == 200 and first.json()["total"] == 2
    assert first.json()["items"][0]["id"] != second.json()["items"][0]["id"]
    denied = auth_client.get(
        "/api/v1/leave-requests/team",
        headers=headers,
        params={"employee_id": scenario.employees["employee_b"].id},
    )
    assert denied.status_code == 403
    for values in [{"page_size": 101}, {"status": "invalid"}, {"page": 0}]:
        assert (
            auth_client.get(
                "/api/v1/leave-requests/team", headers=headers, params=values
            ).status_code
            == 422
        )


ENDPOINTS: list[tuple[str, str, dict[str, Any] | None]] = [
    ("GET", "/leave/options", None),
    ("POST", "/leave-requests", {}),
    ("GET", "/leave-requests", None),
    ("GET", "/leave-requests/team", None),
    ("GET", "/leave-requests/1", None),
    ("POST", "/leave-requests/1/approve", {}),
    ("POST", "/leave-requests/1/reject", {}),
    ("POST", "/leave-requests/1/cancel", None),
]


@pytest.mark.parametrize("method,path,payload", ENDPOINTS)
def test_leave_endpoints_require_authentication(
    auth_client: TestClient, method: str, path: str, payload: dict[str, Any] | None
) -> None:
    assert auth_client.request(method, f"/api/v1{path}", json=payload).status_code == 401


@pytest.mark.parametrize("method,path,payload", ENDPOINTS)
def test_leave_endpoints_require_password_change(
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

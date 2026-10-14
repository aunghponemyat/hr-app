import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Permission, RolePermission, TeamManager
from tests.attendance_support import AttendanceClock
from tests.authz_support import AuthzScenario
from tests.leave_support import leave_payload, leave_record
from tests.test_auth import bearer, login_token


@pytest.mark.parametrize(
    "actor,expected",
    [
        ("employee_a", {"manager_a"}),
        ("employee_b", {"manager_b"}),
        ("unassigned", {"hr", "c_level"}),
        ("manager_a", {"hr", "c_level"}),
        ("hr", {"c_level"}),
    ],
)
def test_eligible_manager_team_and_fallback_rules(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    actor: str,
    expected: set[str],
) -> None:
    headers = bearer(login_token(auth_client, scenario.employees[actor], initial_password))
    response = auth_client.get("/api/v1/leave/options", headers=headers)
    assert response.status_code == 200
    assert {row["id"] for row in response.json()["managers"]} == {
        scenario.employees[key].id for key in expected
    }


@pytest.mark.parametrize("change", ["removed", "inactive", "permission"])
def test_manager_removal_deactivation_or_permission_loss_falls_back_and_revokes_decision(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
    change: str,
) -> None:
    employee, manager = scenario.employees["employee_a"], scenario.employees["manager_a"]
    row = leave_record(seeded_session, employee, manager)
    seeded_session.add(row)
    manager_headers = bearer(login_token(auth_client, manager, initial_password))
    if change == "removed":
        scenario.managers["a"].removed_at = attendance_clock.now()
    elif change == "inactive":
        manager.is_active = False
    else:
        permission = seeded_session.scalar(
            select(Permission.id).where(Permission.code == "leave.decide.team")
        )
        seeded_session.execute(
            delete(RolePermission).where(
                RolePermission.role_id == manager.role_id,
                RolePermission.permission_id == permission,
            )
        )
    seeded_session.commit()
    headers = bearer(login_token(auth_client, employee, initial_password))
    options = auth_client.get("/api/v1/leave/options", headers=headers).json()
    assert {item["id"] for item in options["managers"]} == {
        scenario.employees[key].id for key in {"hr", "c_level"}
    }
    response = auth_client.post(
        "/api/v1/leave-requests", headers=headers, json=leave_payload(seeded_session, manager)
    )
    assert response.status_code == 422 and response.json()["code"] == "INELIGIBLE_MANAGER"
    assert auth_client.post(
        f"/api/v1/leave-requests/{row.id}/approve", headers=manager_headers
    ).status_code == (401 if change == "inactive" else 403)


def test_only_selected_manager_can_decide_even_when_other_manager_manages_same_team(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
) -> None:
    other = scenario.employees["manager_b"]
    seeded_session.add(TeamManager(team_id=scenario.teams["a"].id, employee_id=other.id))
    row = leave_record(
        seeded_session, scenario.employees["employee_a"], scenario.employees["manager_a"]
    )
    seeded_session.add(row)
    headers = bearer(login_token(auth_client, other, initial_password))
    assert auth_client.get(f"/api/v1/leave-requests/{row.id}", headers=headers).status_code == 200
    response = auth_client.post(f"/api/v1/leave-requests/{row.id}/approve", headers=headers)
    assert response.status_code == 403 and response.json()["code"] == "NOT_SELECTED_MANAGER"


def test_ineligible_other_team_self_and_fallback_selection_and_names(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
) -> None:
    employee = scenario.employees["employee_a"]
    scenario.employees["manager_a"].display_name = "Team Lead"
    headers = bearer(login_token(auth_client, employee, initial_password))
    options = auth_client.get("/api/v1/leave/options", headers=headers).json()
    assert options["managers"][0]["name"] == "Team Lead"
    for key in ["employee_a", "employee_b", "manager_b", "hr"]:
        response = auth_client.post(
            "/api/v1/leave-requests",
            headers=headers,
            json=leave_payload(seeded_session, scenario.employees[key]),
        )
        assert response.status_code == 422 and response.json()["code"] == "INELIGIBLE_MANAGER"


def test_no_active_manager_returns_empty_choices(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
) -> None:
    for key in ["hr", "c_level"]:
        scenario.employees[key].is_active = False
    headers = bearer(login_token(auth_client, scenario.employees["unassigned"], initial_password))
    assert auth_client.get("/api/v1/leave/options", headers=headers).json()["managers"] == []


def test_team_change_revokes_selected_manager_decision(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
) -> None:
    row = leave_record(
        seeded_session, scenario.employees["employee_a"], scenario.employees["manager_a"]
    )
    seeded_session.add(row)
    headers = bearer(login_token(auth_client, scenario.employees["manager_a"], initial_password))
    scenario.employees["employee_a"].team_id = scenario.teams["b"].id
    seeded_session.commit()
    assert (
        auth_client.post(f"/api/v1/leave-requests/{row.id}/approve", headers=headers).status_code
        == 403
    )
    assert auth_client.get("/api/v1/leave-requests/team", headers=headers).json()["items"] == []

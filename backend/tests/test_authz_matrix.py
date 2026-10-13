import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Permission, Role, RolePermission, TeamManager, TeamMember
from app.utils.time import utc_now
from tests.authz_support import AuthzScenario
from tests.test_auth import bearer, login_token

ACTORS = ["employee_a", "senior", "manager_a", "hr", "c_level"]


@pytest.mark.parametrize("actor", ACTORS)
def test_me_allowed_for_every_seeded_role(
    authz_client: TestClient, scenario: AuthzScenario, initial_password: SecretStr, actor: str
) -> None:
    employee = scenario.employees[actor]
    token = login_token(authz_client, employee, initial_password)
    response = authz_client.get("/api/v1/me", headers=bearer(token))
    assert response.status_code == 200 and response.json()["id"] == employee.id


@pytest.mark.parametrize("actor", ACTORS)
@pytest.mark.parametrize("target", ["self", "employee_a", "employee_b", "unassigned"])
def test_attendance_target_role_scope_matrix(
    authz_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    actor: str,
    target: str,
) -> None:
    caller = scenario.employees[actor]
    employee = caller if target == "self" else scenario.employees[target]
    token = login_token(authz_client, caller, initial_password)
    allowed = (
        actor in {"hr", "c_level"}
        or employee.id == caller.id
        or (actor == "manager_a" and employee.team_id == scenario.teams["a"].id)
    )
    response = authz_client.get(
        "/api/v1/authz/attendance/target",
        headers=bearer(token),
        params={"employee_id": employee.id},
    )
    assert response.status_code == (200 if allowed else 403)
    if not allowed:
        assert response.json()["code"] == "OUT_OF_SCOPE"


@pytest.mark.parametrize("actor", ACTORS)
@pytest.mark.parametrize("target", ["employee_a", "employee_b", "unassigned"])
def test_attendance_edit_role_scope_matrix(
    authz_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    actor: str,
    target: str,
) -> None:
    caller, employee = scenario.employees[actor], scenario.employees[target]
    token = login_token(authz_client, caller, initial_password)
    allowed = actor in {"hr", "c_level"} or (
        actor == "manager_a" and employee.team_id == scenario.teams["a"].id
    )
    response = authz_client.post(
        "/api/v1/authz/attendance/edit", headers=bearer(token), json={"employee_id": employee.id}
    )
    assert response.status_code == (200 if allowed else 403)
    if not allowed:
        assert response.json()["code"] == (
            "OUT_OF_SCOPE" if actor == "manager_a" else "PERMISSION_DENIED"
        )


@pytest.mark.parametrize("actor", ACTORS)
@pytest.mark.parametrize("resource", ["attendance", "leave"])
def test_lists_filter_effective_scope(
    authz_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    actor: str,
    resource: str,
) -> None:
    caller = scenario.employees[actor]
    token = login_token(authz_client, caller, initial_password)
    expected = (
        scenario.ids()
        if actor in {"hr", "c_level"}
        else (scenario.team_ids("a") | {caller.id} if actor == "manager_a" else {caller.id})
    )
    response = authz_client.get(f"/api/v1/authz/{resource}", headers=bearer(token))
    assert response.status_code == 200
    assert set(response.json()["ids"]) == expected
    assert response.json()["total"] == len(expected)


@pytest.mark.parametrize("actor", ACTORS)
def test_team_members_gate_and_scope(
    authz_client: TestClient, scenario: AuthzScenario, initial_password: SecretStr, actor: str
) -> None:
    token = login_token(authz_client, scenario.employees[actor], initial_password)
    response = authz_client.get("/api/v1/team/members", headers=bearer(token))
    if actor in {"employee_a", "senior"}:
        assert response.status_code == 403 and response.json()["code"] == "PERMISSION_DENIED"
    else:
        expected = scenario.ids() if actor in {"hr", "c_level"} else scenario.team_ids("a")
        assert response.status_code == 200 and set(response.json()["ids"]) == expected


@pytest.mark.parametrize("actor", ACTORS)
def test_admin_create_permission_is_any_only(
    authz_client: TestClient, scenario: AuthzScenario, initial_password: SecretStr, actor: str
) -> None:
    token = login_token(authz_client, scenario.employees[actor], initial_password)
    response = authz_client.get("/api/v1/authz/admin-create", headers=bearer(token))
    assert response.status_code == (200 if actor in {"hr", "c_level"} else 403)


@pytest.mark.parametrize("actor", ACTORS)
def test_nonexistent_target_policy(
    authz_client: TestClient, scenario: AuthzScenario, initial_password: SecretStr, actor: str
) -> None:
    token = login_token(authz_client, scenario.employees[actor], initial_password)
    response = authz_client.get(
        "/api/v1/authz/attendance/target", headers=bearer(token), params={"employee_id": 2**63}
    )
    expected_status = 404 if actor in {"manager_a", "hr", "c_level"} else 403
    assert response.status_code == expected_status
    assert response.json()["code"] == ("NOT_FOUND" if expected_status == 404 else "OUT_OF_SCOPE")


def test_removing_manager_revokes_team_access_immediately(
    authz_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    seeded_session: Session,
) -> None:
    token = login_token(authz_client, scenario.employees["manager_a"], initial_password)
    target = scenario.employees["employee_a"].id
    assert (
        authz_client.get(
            "/api/v1/authz/attendance/target", headers=bearer(token), params={"employee_id": target}
        ).status_code
        == 200
    )
    scenario.managers["a"].removed_at = utc_now()
    seeded_session.flush()
    denied = authz_client.get(
        "/api/v1/authz/attendance/target", headers=bearer(token), params={"employee_id": target}
    )
    assert denied.status_code == 403 and denied.json()["code"] == "OUT_OF_SCOPE"
    listed = authz_client.get("/api/v1/authz/attendance", headers=bearer(token))
    assert listed.json()["ids"] == [scenario.employees["manager_a"].id]


def test_targets_use_current_team_not_membership_history(
    authz_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    seeded_session: Session,
) -> None:
    token = login_token(authz_client, scenario.employees["manager_a"], initial_password)
    employee = scenario.employees["employee_a"]
    old = seeded_session.execute(
        select(TeamMember).where(
            TeamMember.employee_id == employee.id, TeamMember.left_at.is_(None)
        )
    ).scalar_one()
    now = utc_now()
    old.left_at = now
    employee.team = scenario.teams["b"]
    seeded_session.add(
        TeamMember(team_id=scenario.teams["b"].id, employee_id=employee.id, joined_at=now)
    )
    seeded_session.flush()
    response = authz_client.get(
        "/api/v1/authz/attendance/target",
        headers=bearer(token),
        params={"employee_id": employee.id},
    )
    assert response.status_code == 403
    assert (
        employee.id
        not in authz_client.get("/api/v1/authz/attendance", headers=bearer(token)).json()["ids"]
    )


def test_manager_can_manage_multiple_teams(
    authz_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    seeded_session: Session,
) -> None:
    manager = scenario.employees["manager_a"]
    seeded_session.add(TeamManager(team_id=scenario.teams["b"].id, employee_id=manager.id))
    seeded_session.flush()
    token = login_token(authz_client, manager, initial_password)
    response = authz_client.get("/api/v1/authz/attendance", headers=bearer(token))
    assert set(response.json()["ids"]) == scenario.team_ids("a") | scenario.team_ids("b")


def test_manager_self_access_is_independent_of_current_team(
    authz_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    seeded_session: Session,
) -> None:
    manager = scenario.employees["manager_a"]
    membership = seeded_session.execute(
        select(TeamMember).where(
            TeamMember.employee_id == manager.id,
            TeamMember.left_at.is_(None),
        )
    ).scalar_one()
    membership.left_at = utc_now()
    manager.team = None
    seeded_session.flush()
    token = login_token(authz_client, manager, initial_password)
    self_read = authz_client.get(
        "/api/v1/authz/attendance/target", headers=bearer(token), params={"employee_id": manager.id}
    )
    assert self_read.status_code == 200
    listed = authz_client.get("/api/v1/team/members", headers=bearer(token))
    assert set(listed.json()["ids"]) == scenario.team_ids("a") | {manager.id}


def test_role_change_takes_effect_with_existing_access_token(
    authz_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    seeded_session: Session,
) -> None:
    manager = scenario.employees["manager_a"]
    token = login_token(authz_client, manager, initial_password)
    manager.role_id = seeded_session.execute(
        select(Role.id).where(Role.name == "employee")
    ).scalar_one()
    seeded_session.flush()
    response = authz_client.get("/api/v1/team/members", headers=bearer(token))
    assert response.status_code == 403 and response.json()["code"] == "PERMISSION_DENIED"
    assert (
        authz_client.get("/api/v1/me", headers=bearer(token)).json()["role"]["name"] == "employee"
    )


def test_grant_revocation_takes_effect_without_role_change(
    authz_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    seeded_session: Session,
) -> None:
    manager = scenario.employees["manager_a"]
    token = login_token(authz_client, manager, initial_password)
    permission_id = seeded_session.execute(
        select(Permission.id).where(Permission.code == "attendance.read.team")
    ).scalar_one()
    seeded_session.execute(
        delete(RolePermission).where(
            RolePermission.role_id == manager.role_id, RolePermission.permission_id == permission_id
        )
    )
    response = authz_client.get("/api/v1/authz/attendance", headers=bearer(token))
    assert response.json()["ids"] == [manager.id]
    assert (
        "attendance.read.team"
        not in authz_client.get("/api/v1/me", headers=bearer(token)).json()["permissions"]
    )


def test_password_change_gate_precedes_permission_check(
    authz_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    seeded_session: Session,
) -> None:
    employee = scenario.employees["employee_a"]
    employee.must_change_password = True
    seeded_session.flush()
    token = login_token(authz_client, employee, initial_password)
    response = authz_client.get("/api/v1/team/members", headers=bearer(token))
    assert response.status_code == 403 and response.json()["code"] == "PASSWORD_CHANGE_REQUIRED"
    assert authz_client.get("/api/v1/me", headers=bearer(token)).status_code == 200


def test_absent_permission_does_not_leak_missing_target(
    authz_client: TestClient, scenario: AuthzScenario, initial_password: SecretStr
) -> None:
    token = login_token(authz_client, scenario.employees["employee_a"], initial_password)
    response = authz_client.post(
        "/api/v1/authz/attendance/edit", headers=bearer(token), json={"employee_id": 2**63}
    )
    assert response.status_code == 403 and response.json()["code"] == "PERMISSION_DENIED"

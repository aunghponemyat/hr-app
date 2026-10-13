from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, Role, TeamManager, TeamMember
from tests.authz_support import AuthzScenario
from tests.test_auth import bearer, login_token


@pytest.mark.parametrize("move_via", ["employee_patch", "team_member"])
def test_moves_and_removal_preserve_membership_history(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    seeded_session: Session,
    move_via: str,
) -> None:
    headers = bearer(login_token(auth_client, scenario.employees["hr"], initial_password))
    employee = scenario.employees["employee_a"]
    employee_id = employee.id
    for destination in ["b", "a", "a"]:
        team_id = scenario.teams[destination].id
        response = (
            auth_client.patch(
                f"/api/v1/admin/employees/{employee_id}", headers=headers, json={"team_id": team_id}
            )
            if move_via == "employee_patch"
            else auth_client.post(
                f"/api/v1/admin/teams/{team_id}/members",
                headers=headers,
                json={"employee_id": employee_id},
            )
        )
        assert response.status_code == 200, response.text
    histories = seeded_session.scalars(
        select(TeamMember)
        .where(TeamMember.employee_id == employee_id)
        .order_by(TeamMember.joined_at)
    ).all()
    assert len(histories) == 3 and [row.team_id for row in histories] == [
        scenario.teams["a"].id,
        scenario.teams["b"].id,
        scenario.teams["a"].id,
    ]
    assert [row.left_at is None for row in histories] == [False, False, True]
    assert (
        histories[0].left_at == histories[1].joined_at
        and histories[1].left_at == histories[2].joined_at
    )
    removed = auth_client.delete(
        f"/api/v1/admin/teams/{scenario.teams['a'].id}/members/{employee_id}", headers=headers
    )
    assert removed.status_code == 200
    seeded_session.refresh(employee)
    assert employee.team_id is None
    assert not seeded_session.scalars(
        select(TeamMember).where(
            TeamMember.employee_id == employee_id, TeamMember.left_at.is_(None)
        )
    ).all()
    manager_headers = bearer(
        login_token(auth_client, scenario.employees["manager_a"], initial_password)
    )
    assert employee_id not in {
        row["id"]
        for row in auth_client.get("/api/v1/team/members", headers=manager_headers).json()["items"]
    }


@pytest.mark.parametrize("change", ["demote", "deactivate"])
def test_manager_losing_eligibility_closes_assignments_without_erasing_history(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    seeded_session: Session,
    change: str,
) -> None:
    manager = scenario.employees["manager_a"]
    manager_token = login_token(auth_client, manager, initial_password)
    headers = bearer(login_token(auth_client, scenario.employees["hr"], initial_password))
    payload = (
        {"is_active": False}
        if change == "deactivate"
        else {"role_id": scenario.employees["employee_a"].role_id}
    )
    changed = auth_client.patch(
        f"/api/v1/admin/employees/{manager.id}", headers=headers, json=payload
    )
    assert changed.status_code == 200
    assignment = seeded_session.scalars(
        select(TeamManager).where(TeamManager.employee_id == manager.id)
    ).one()
    assert assignment.removed_at is not None
    denied = auth_client.get("/api/v1/team/members", headers=bearer(manager_token))
    assert denied.status_code == (401 if change == "deactivate" else 403)
    if change == "deactivate":
        assert (
            auth_client.patch(
                f"/api/v1/admin/employees/{manager.id}", headers=headers, json={"is_active": True}
            ).status_code
            == 200
        )
        assert (
            auth_client.get(
                f"/api/v1/admin/teams/{scenario.teams['a'].id}/managers", headers=headers
            ).json()["total"]
            == 0
        )
        assert auth_client.get("/api/v1/me", headers=bearer(manager_token)).status_code == 401


def test_remove_and_reassign_manager_preserves_two_rows(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    seeded_session: Session,
) -> None:
    headers = bearer(login_token(auth_client, scenario.employees["hr"], initial_password))
    path = f"/api/v1/admin/teams/{scenario.teams['a'].id}/managers"
    manager_id = scenario.employees["manager_a"].id
    assert auth_client.delete(f"{path}/{manager_id}", headers=headers).status_code == 200
    assert (
        auth_client.post(path, headers=headers, json={"employee_id": manager_id}).status_code == 200
    )
    rows = seeded_session.scalars(
        select(TeamManager)
        .where(TeamManager.employee_id == manager_id)
        .order_by(TeamManager.assigned_at)
    ).all()
    assert len(rows) == 2 and rows[0].removed_at is not None and rows[1].removed_at is None


@pytest.mark.parametrize("kind", ["role", "deactivate"])
def test_last_admin_is_protected_and_uses_permissions(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    seeded_session: Session,
    kind: str,
) -> None:
    hr = scenario.employees["hr"]
    headers = bearer(login_token(auth_client, hr, initial_password))
    # A role label change does not affect the permission-defined admin check.
    role = seeded_session.get(Role, hr.role_id)
    assert role is not None
    role.name = "custom_admin_label"
    seeded_session.commit()
    other = scenario.employees["c_level"]
    assert (
        auth_client.patch(
            f"/api/v1/admin/employees/{other.id}", headers=headers, json={"is_active": False}
        ).status_code
        == 200
    )
    payload = (
        {"is_active": False}
        if kind == "deactivate"
        else {"role_id": scenario.employees["employee_a"].role_id}
    )
    response = auth_client.patch(f"/api/v1/admin/employees/{hr.id}", headers=headers, json=payload)
    assert response.status_code == 409 and response.json()["code"] == "LAST_ADMIN"
    current = auth_client.get("/api/v1/me", headers=headers)
    assert current.status_code == 200 and current.json()["role"]["name"] == "custom_admin_label"
    assert auth_client.get(f"/api/v1/admin/employees/{hr.id}", headers=headers).json()["is_active"]


def test_invalid_team_move_rolls_back_other_employee_fields_and_audit(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    seeded_session: Session,
) -> None:
    headers = bearer(login_token(auth_client, scenario.employees["hr"], initial_password))
    employee = scenario.employees["employee_a"]
    before = employee.first_name
    response = auth_client.patch(
        f"/api/v1/admin/employees/{employee.id}",
        headers=headers,
        json={"first_name": "Changed", "team_id": 2**63},
    )
    assert response.status_code == 404
    seeded_session.refresh(employee)
    assert employee.first_name == before and employee.team_id == scenario.teams["a"].id
    assert not seeded_session.scalars(select(AuditLog)).all()


def test_inactive_assignees_and_unqualified_managers_rejected(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
) -> None:
    headers = bearer(login_token(auth_client, scenario.employees["hr"], initial_password))
    employee_id = scenario.employees["employee_a"].id
    path = f"/api/v1/admin/teams/{scenario.teams['a'].id}"
    response = auth_client.post(
        f"{path}/managers", headers=headers, json={"employee_id": employee_id}
    )
    assert response.status_code == 422 and response.json()["code"] == "INELIGIBLE_MANAGER"
    assert (
        auth_client.patch(
            f"/api/v1/admin/employees/{employee_id}", headers=headers, json={"is_active": False}
        ).status_code
        == 200
    )
    for suffix in ["members", "managers"]:
        assert (
            auth_client.post(
                f"{path}/{suffix}", headers=headers, json={"employee_id": employee_id}
            ).status_code
            == 422
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("latitude", 91),
        ("latitude", -91),
        ("longitude", 181),
        ("longitude", -181),
        ("allowed_radius_m", 49),
        ("allowed_radius_m", 101),
        ("latitude", "13.1234567"),
        ("latitude", "NaN"),
        ("name", " "),
    ],
)
def test_invalid_location_fields(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    field: str,
    value: Any,
) -> None:
    headers = bearer(login_token(auth_client, scenario.employees["hr"], initial_password))
    payload = {"name": "Office", "latitude": 13, "longitude": 100, field: value}
    assert (
        auth_client.post("/api/v1/admin/work-locations", headers=headers, json=payload).status_code
        == 422
    )

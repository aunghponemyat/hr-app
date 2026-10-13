import json
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import verify_password
from app.models import AuditLog, Employee, RefreshSession, TeamMember
from app.utils.time import utc_now
from tests.authz_support import AuthzScenario
from tests.test_auth import bearer, login_token

ADMIN_CASES = [
    ("GET", "/admin/employees", None),
    (
        "POST",
        "/admin/employees",
        {
            "first_name": "New",
            "last_name": "User",
            "role_id": 1,
            "default_password": "InitialPass123",
        },
    ),
    ("GET", "/admin/employees/{employee}", None),
    ("PATCH", "/admin/employees/{employee}", {"display_name": "New name"}),
    ("POST", "/admin/employees/{employee}/reset-password", {"default_password": "ResetPass123"}),
    ("GET", "/admin/utils/generate-password", None),
    ("GET", "/admin/roles", None),
    ("GET", "/admin/teams", None),
    ("POST", "/admin/teams", {"name": "New team"}),
    ("GET", "/admin/teams/{team}", None),
    ("PATCH", "/admin/teams/{team}", {"name": "Renamed"}),
    ("DELETE", "/admin/teams/{team}", None),
    ("GET", "/admin/teams/{team}/members", None),
    ("POST", "/admin/teams/{team}/members", {"employee_id": 1}),
    ("DELETE", "/admin/teams/{team}/members/{employee}", None),
    ("GET", "/admin/teams/{team}/managers", None),
    ("POST", "/admin/teams/{team}/managers", {"employee_id": 1}),
    ("DELETE", "/admin/teams/{team}/managers/{employee}", None),
    ("GET", "/admin/teams/{team}/locations", None),
    ("POST", "/admin/teams/{team}/locations", {"work_location_id": 1}),
    ("DELETE", "/admin/teams/{team}/locations/1", None),
    ("GET", "/admin/work-locations", None),
    ("POST", "/admin/work-locations", {"name": "Office", "latitude": 13, "longitude": 100}),
    ("GET", "/admin/work-locations/1", None),
    ("PATCH", "/admin/work-locations/1", {"allowed_radius_m": 80}),
    ("DELETE", "/admin/work-locations/1", None),
]


@pytest.mark.parametrize("actor", ["employee_a", "manager_a"])
@pytest.mark.parametrize("method,path,payload", ADMIN_CASES)
def test_every_admin_endpoint_denies_non_admin(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    actor: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None,
) -> None:
    token = login_token(auth_client, scenario.employees[actor], initial_password)
    path = path.format(employee=scenario.employees["employee_a"].id, team=scenario.teams["a"].id)
    response = auth_client.request(method, f"/api/v1{path}", headers=bearer(token), json=payload)
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "PERMISSION_DENIED"


@pytest.mark.parametrize("actor", ["hr", "c_level"])
def test_admin_setup_and_all_crud_happy_paths(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    seeded_session: Session,
    actor: str,
    auth_settings: Settings,
) -> None:
    token = login_token(auth_client, scenario.employees[actor], initial_password)
    headers = bearer(token)

    def call(
        method: str, path: str, payload: dict[str, Any] | None = None, status: int = 200
    ) -> Any:
        response = auth_client.request(method, f"/api/v1{path}", headers=headers, json=payload)
        assert response.status_code == status, response.text
        assert response.headers["cache-control"] == "no-store"
        return response.json()

    roles = call("GET", "/admin/roles")["items"]
    manager_role = next(role["id"] for role in roles if role["name"] == "reporting_manager")
    employee_role = next(role["id"] for role in roles if role["name"] == "employee")
    assert all("permissions" in role for role in roles)
    generated = call("GET", "/admin/utils/generate-password")["default_password"]
    assert (
        len(generated) == 12
        and any(c.isalpha() for c in generated)
        and any(c.isdigit() for c in generated)
    )
    team = call("POST", "/admin/teams", {"name": "New Operations", "description": "Setup"}, 201)
    team_path = f"/admin/teams/{team['id']}"
    assert call("GET", team_path)["name"] == "New Operations"
    assert team["id"] in {row["id"] for row in call("GET", "/admin/teams")["items"]}
    assert call("PATCH", team_path, {"description": None})["description"] is None
    location = call(
        "POST",
        "/admin/work-locations",
        {"name": "HQ", "latitude": "13.756300", "longitude": "100.501800"},
        201,
    )
    location_path = f"/admin/work-locations/{location['id']}"
    assert call("GET", location_path)["allowed_radius_m"] == 100
    assert call("PATCH", location_path, {"allowed_radius_m": 80})["allowed_radius_m"] == 80
    assert call("GET", "/admin/work-locations")["total"] == 1
    call("POST", f"{team_path}/locations", {"work_location_id": location["id"]})
    call("POST", f"{team_path}/locations", {"work_location_id": location["id"]})
    assert call("GET", f"{team_path}/locations")["total"] == 1
    manager = call(
        "POST",
        "/admin/employees",
        {
            "first_name": "New",
            "last_name": "Manager",
            "role_id": manager_role,
            "team_id": team["id"],
            "default_password": generated,
        },
        201,
    )
    employee = call(
        "POST",
        "/admin/employees",
        {
            "first_name": "New",
            "last_name": "Employee",
            "role_id": employee_role,
            "team_id": team["id"],
            "default_password": generated,
        },
        201,
    )
    assert manager["employee_id"] != employee["employee_id"]
    assert employee["employee_id"].startswith("EMP") and employee["must_change_password"]
    assert employee["default_password"] == generated
    assert employee["created_at"].endswith("+07:00")
    assert call("GET", f"/admin/employees/{employee['id']}").get("default_password") is None
    assert "password_hash" not in json.dumps(call("GET", "/admin/employees"))
    updated = call(
        "PATCH",
        f"/admin/employees/{employee['id']}",
        {"position": "Analyst", "display_name": "Friendly"},
    )
    assert updated["position"] == "Analyst" and updated["employee_id"] == employee["employee_id"]
    call("POST", f"{team_path}/managers", {"employee_id": manager["id"]})
    call("POST", f"{team_path}/managers", {"employee_id": manager["id"]})
    assert call("GET", f"{team_path}/managers")["total"] == 1
    manager_model = seeded_session.get(Employee, manager["id"])
    assert manager_model is not None
    manager_token = login_token(auth_client, manager_model, SecretStr(generated))
    blocked = auth_client.get("/api/v1/team/members", headers=bearer(manager_token))
    assert blocked.status_code == 403 and blocked.json()["code"] == "PASSWORD_CHANGE_REQUIRED"
    changed = auth_client.post(
        "/api/v1/auth/change-password",
        headers=bearer(manager_token),
        json={
            "current_password": generated,
            "new_password": "ChangedPass123",
        },
    )
    assert changed.status_code == 200
    manager_headers = bearer(changed.json()["access_token"])
    roster = auth_client.get("/api/v1/team/members", headers=manager_headers)
    assert roster.status_code == 200 and {row["id"] for row in roster.json()["items"]} == {
        manager["id"],
        employee["id"],
    }
    assert call("GET", f"{team_path}/members")["total"] == 2
    call("POST", f"{team_path}/members", {"employee_id": scenario.employees["unassigned"].id})
    call("DELETE", f"{team_path}/members/{scenario.employees['unassigned'].id}")
    call("DELETE", f"{team_path}/managers/{manager['id']}")
    roster = auth_client.get("/api/v1/team/members", headers=manager_headers)
    assert {row["id"] for row in roster.json()["items"]} == {manager["id"]}
    call(
        "POST",
        f"/admin/employees/{employee['id']}/reset-password",
        {"default_password": "ResetPass123"},
    )
    call("DELETE", f"{team_path}/locations/{location['id']}")
    call("DELETE", location_path)
    disposable = call("POST", "/admin/teams", {"name": "Disposable"}, 201)
    call("DELETE", f"/admin/teams/{disposable['id']}")
    assert call("GET", "/admin/work-locations")["total"] == 0
    histories = seeded_session.scalars(
        select(TeamMember).where(TeamMember.employee_id == employee["id"])
    ).all()
    assert len(histories) == 1 and histories[0].left_at is None
    logs = seeded_session.scalars(select(AuditLog)).all()
    assert {
        "employee.create",
        "employee.update",
        "employee.team_change",
        "employee.password_reset",
        "team.manager_assign",
        "team.manager_remove",
        "team.location_link",
        "team.location_unlink",
        "team.delete",
        "location.delete",
    } <= {log.action for log in logs}
    audit_json = json.dumps([{"before": log.before_json, "after": log.after_json} for log in logs])
    assert (
        generated not in audit_json
        and "ResetPass123" not in audit_json
        and "password_hash" not in audit_json
    )
    assert auth_settings.app_timezone == "Asia/Bangkok"


@pytest.mark.parametrize("actor", ["employee_a", "senior", "manager_a", "hr", "c_level"])
def test_production_roster_role_scope_and_pagination(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    actor: str,
) -> None:
    token = login_token(auth_client, scenario.employees[actor], initial_password)
    response = auth_client.get("/api/v1/team/members?page_size=2", headers=bearer(token))
    if actor in {"employee_a", "senior"}:
        assert response.status_code == 403
        return
    expected = scenario.ids() if actor in {"hr", "c_level"} else scenario.team_ids("a")
    assert response.status_code == 200 and response.json()["total"] == len(expected)
    assert len(response.json()["items"]) == 2
    ids = {row["id"] for row in response.json()["items"]}
    second = auth_client.get("/api/v1/team/members?page_size=2&page=2", headers=bearer(token))
    assert ids.isdisjoint(row["id"] for row in second.json()["items"])
    assert ids <= expected


def test_reset_revokes_tokens_clears_lockout_and_forces_change(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    seeded_session: Session,
) -> None:
    employee = scenario.employees["employee_a"]
    old_token = login_token(auth_client, employee, initial_password)
    old_refresh = auth_client.cookies.get("refresh_token")
    admin_token = login_token(auth_client, scenario.employees["hr"], initial_password)
    employee.failed_login_count = 5
    employee.locked_until = utc_now() + timedelta(minutes=15)
    seeded_session.commit()
    reset = auth_client.post(
        f"/api/v1/admin/employees/{employee.id}/reset-password",
        headers=bearer(admin_token),
        json={"default_password": "Replacement123"},
    )
    assert reset.status_code == 200 and reset.json()["default_password"] == "Replacement123"
    seeded_session.refresh(employee)
    assert (
        employee.must_change_password
        and employee.failed_login_count == 0
        and employee.locked_until is None
    )
    assert verify_password("Replacement123", employee.password_hash)[0]
    assert auth_client.get("/api/v1/me", headers=bearer(old_token)).status_code == 401
    auth_client.cookies.clear()
    assert old_refresh is not None
    auth_client.cookies.set("refresh_token", old_refresh, path="/api/v1/auth")
    assert auth_client.post("/api/v1/auth/refresh").status_code == 401
    token = login_token(auth_client, employee, SecretStr("Replacement123"))
    assert auth_client.get("/api/v1/me", headers=bearer(token)).json()["must_change_password"]
    assert (
        auth_client.patch(
            "/api/v1/me", headers=bearer(token), json={"display_name": "Blocked"}
        ).status_code
        == 403
    )
    previous = seeded_session.scalars(
        select(RefreshSession).where(
            RefreshSession.employee_id == employee.id, RefreshSession.revoked_at.is_not(None)
        )
    ).all()
    assert previous


@pytest.mark.parametrize(
    "payload",
    [
        {"employee_id": "CHANGE"},
        {"role_id": 1},
        {"team_id": 1},
        {"is_active": False},
        {},
        {"display_name": " "},
    ],
)
def test_profile_rejects_non_display_fields_and_empty_patch(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    payload: dict[str, Any],
) -> None:
    token = login_token(auth_client, scenario.employees["employee_a"], initial_password)
    assert auth_client.patch("/api/v1/me", headers=bearer(token), json=payload).status_code == 422


def test_profile_update_clear_and_authorization_failure(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
) -> None:
    token = login_token(auth_client, scenario.employees["employee_a"], initial_password)
    for name in ["New display", None]:
        response = auth_client.patch(
            "/api/v1/me", headers=bearer(token), json={"display_name": name}
        )
        assert response.status_code == 200 and response.json()["display_name"] == name
    assert auth_client.patch("/api/v1/me", json={"display_name": "Anonymous"}).status_code == 401


@pytest.mark.parametrize(
    "payload",
    [
        {"employee_id": "CHANGE"},
        {"first_name": None},
        {"last_name": None},
        {"role_id": None},
        {"is_active": None},
        {},
        {"first_name": " "},
    ],
)
def test_employee_patch_rejects_immutable_and_invalid_fields(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    payload: dict[str, Any],
) -> None:
    token = login_token(auth_client, scenario.employees["hr"], initial_password)
    employee = scenario.employees["employee_a"]
    response = auth_client.patch(
        f"/api/v1/admin/employees/{employee.id}", headers=bearer(token), json=payload
    )
    assert response.status_code == 422
    assert (
        auth_client.get(f"/api/v1/admin/employees/{employee.id}", headers=bearer(token)).json()[
            "employee_id"
        ]
        == employee.employee_id
    )

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import (
    Attendance,
    AuditLog,
    Permission,
    RolePermission,
    Team,
    TeamManager,
    TeamMember,
)
from app.models.enums import AttendanceStatus, WorkMode
from tests.authz_support import AuthzScenario
from tests.test_auth import bearer, login_token


def test_employee_filters_search_and_page_validation(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
) -> None:
    headers = bearer(login_token(auth_client, scenario.employees["hr"], initial_password))
    employee = scenario.employees["employee_a"]
    path = "/api/v1/admin/employees"
    response = auth_client.get(
        path,
        headers=headers,
        params={
            "search": employee.employee_id,
            "team_id": employee.team_id,
            "role_id": employee.role_id,
            "is_active": True,
        },
    )
    assert response.status_code == 200 and [row["id"] for row in response.json()["items"]] == [
        employee.id
    ]
    assert auth_client.get(path, headers=headers, params={"search": "%"}).json()["total"] == 0
    literal_matches = {
        employee.id
        for employee in scenario.employees.values()
        if any(
            "_" in (value or "")
            for value in (
                employee.employee_id,
                employee.first_name,
                employee.last_name,
                employee.display_name,
            )
        )
    }
    assert {
        row["id"]
        for row in auth_client.get(path, headers=headers, params={"search": "_"}).json()["items"]
    } == literal_matches
    assert auth_client.get(path, headers=headers, params={"is_active": False}).json()["total"] == 0
    for params in [
        {"page": 0},
        {"page_size": 101},
        {"page_size": 0},
        {"team_id": -1},
        {"unknown": "value"},
    ]:
        assert auth_client.get(path, headers=headers, params=params).status_code == 422
    assert auth_client.get(path, headers=headers, params={"page": 100}).json()["items"] == []


def test_team_delete_keeps_current_and_past_membership_and_manager_history(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    seeded_session: Session,
) -> None:
    headers = bearer(login_token(auth_client, scenario.employees["hr"], initial_password))
    team_id = scenario.teams["a"].id
    path = f"/api/v1/admin/teams/{team_id}"
    blocked = auth_client.delete(path, headers=headers)
    assert blocked.status_code == 409 and blocked.json()["code"] == "TEAM_IN_USE"
    for employee_id in scenario.team_ids("a"):
        assert (
            auth_client.delete(f"{path}/members/{employee_id}", headers=headers).status_code == 200
        )
    assert (
        auth_client.delete(
            f"{path}/managers/{scenario.employees['manager_a'].id}", headers=headers
        ).status_code
        == 200
    )
    assert auth_client.delete(path, headers=headers).status_code == 409
    assert seeded_session.get(Team, team_id) is not None
    assert seeded_session.scalars(select(TeamMember).where(TeamMember.team_id == team_id)).all()
    assert (
        seeded_session.scalars(select(TeamManager).where(TeamManager.team_id == team_id))
        .one()
        .removed_at
        is not None
    )


def test_location_delete_requires_unlink_and_preserves_attendance_reference(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    seeded_session: Session,
    auth_settings: Settings,
) -> None:
    headers = bearer(login_token(auth_client, scenario.employees["hr"], initial_password))
    created = auth_client.post(
        "/api/v1/admin/work-locations",
        headers=headers,
        json={"name": "HQ", "latitude": 13, "longitude": 100},
    )
    assert created.status_code == 201
    location_id = created.json()["id"]
    path = f"/api/v1/admin/work-locations/{location_id}"
    team_path = f"/api/v1/admin/teams/{scenario.teams['a'].id}/locations"
    assert (
        auth_client.post(
            team_path, headers=headers, json={"work_location_id": location_id}
        ).status_code
        == 200
    )
    blocked = auth_client.delete(path, headers=headers)
    assert blocked.status_code == 409 and blocked.json()["code"] == "LOCATION_IN_USE"
    now = datetime(2026, 10, 14, 3, tzinfo=timezone.utc)
    seeded_session.add(
        Attendance(
            employee_id=scenario.employees["employee_a"].id,
            attendance_date=now.astimezone(ZoneInfo(auth_settings.app_timezone)).date(),
            work_mode=WorkMode.ONSITE,
            work_location_id=location_id,
            status=AttendanceStatus.PRESENT,
            clock_in=now,
        )
    )
    seeded_session.commit()
    assert auth_client.delete(f"{team_path}/{location_id}", headers=headers).status_code == 200
    assert auth_client.delete(path, headers=headers).json()["code"] == "LOCATION_IN_USE"
    assert auth_client.get(path, headers=headers).status_code == 200


def test_duplicate_team_name_rolls_back_and_returns_uniform_conflict(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    seeded_session: Session,
) -> None:
    headers = bearer(login_token(auth_client, scenario.employees["hr"], initial_password))
    created = auth_client.post("/api/v1/admin/teams", headers=headers, json={"name": "Unique Team"})
    assert created.status_code == 201
    duplicate = auth_client.post(
        "/api/v1/admin/teams", headers=headers, json={"name": "Unique Team"}
    )
    assert duplicate.status_code == 409 and duplicate.json()["code"] == "CONFLICT"
    assert (
        auth_client.get(f"/api/v1/admin/teams/{created.json()['id']}", headers=headers).status_code
        == 200
    )
    assert (
        len(seeded_session.scalars(select(AuditLog).where(AuditLog.action == "team.create")).all())
        == 1
    )


@pytest.mark.parametrize(
    "path",
    [
        "/admin/employees/9223372036854775808",
        "/admin/teams/9223372036854775808",
        "/admin/work-locations/9223372036854775808",
    ],
)
def test_admin_missing_record_and_anonymous_failure(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    path: str,
) -> None:
    headers = bearer(login_token(auth_client, scenario.employees["hr"], initial_password))
    assert auth_client.get(f"/api/v1{path}", headers=headers).status_code == 404
    assert auth_client.get(f"/api/v1{path}").status_code == 401


@pytest.mark.parametrize("suffix", ["members", "managers", "locations"])
def test_missing_association_removal_is_404(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    suffix: str,
) -> None:
    headers = bearer(login_token(auth_client, scenario.employees["hr"], initial_password))
    path = f"/api/v1/admin/teams/{scenario.teams['a'].id}/{suffix}/9223372036854775808"
    assert auth_client.delete(path, headers=headers).status_code == 404


@pytest.mark.parametrize("password", ["short1", "12345678", "abcdefgh"])
def test_admin_password_policy_and_error_redaction(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    password: str,
) -> None:
    headers = bearer(login_token(auth_client, scenario.employees["hr"], initial_password))
    response = auth_client.post(
        "/api/v1/admin/employees",
        headers=headers,
        json={
            "first_name": "New",
            "last_name": "User",
            "role_id": scenario.employees["employee_a"].role_id,
            "default_password": password,
        },
    )
    assert response.status_code == 422 and password not in response.text
    response = auth_client.post(
        f"/api/v1/admin/employees/{scenario.employees['employee_a'].id}/reset-password",
        headers=headers,
        json={"default_password": password},
    )
    assert response.status_code == 422 and password not in response.text


@pytest.mark.parametrize("payload", [{"role_id": 2**63}, {"team_id": 2**63}])
def test_invalid_creation_references_are_atomic(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    payload: dict[str, Any],
) -> None:
    headers = bearer(login_token(auth_client, scenario.employees["hr"], initial_password))
    response = auth_client.post(
        "/api/v1/admin/employees",
        headers=headers,
        json={
            "first_name": "Invalid",
            "last_name": "Reference",
            "role_id": scenario.employees["employee_a"].role_id,
            "default_password": "InitialPass123",
            **payload,
        },
    )
    assert response.status_code == 404
    assert auth_client.get("/api/v1/admin/employees", headers=headers).json()["total"] == len(
        scenario.ids()
    )


def test_profile_update_denies_revoked_grant_with_existing_token(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    seeded_session: Session,
) -> None:
    employee = scenario.employees["employee_a"]
    headers = bearer(login_token(auth_client, employee, initial_password))
    permission_id = seeded_session.scalar(
        select(Permission.id).where(Permission.code == "profile.update.self")
    )
    seeded_session.execute(
        delete(RolePermission).where(
            RolePermission.role_id == employee.role_id,
            RolePermission.permission_id == permission_id,
        )
    )
    seeded_session.commit()
    response = auth_client.patch("/api/v1/me", headers=headers, json={"display_name": "Denied"})
    assert response.status_code == 403 and response.json()["code"] == "PERMISSION_DENIED"


def test_roster_today_status_uses_office_local_date(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    seeded_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 10, 13, 18, tzinfo=timezone.utc)  # Wednesday in Bangkok.
    monkeypatch.setattr("app.services.roster_service.utc_now", lambda: now)
    seeded_session.add(
        Attendance(
            employee_id=scenario.employees["employee_a"].id,
            attendance_date=now.astimezone(ZoneInfo("Asia/Bangkok")).date(),
            work_mode=WorkMode.REMOTE,
            status=AttendanceStatus.HALF_DAY,
            clock_in=now,
        )
    )
    headers = bearer(login_token(auth_client, scenario.employees["manager_a"], initial_password))
    listed = auth_client.get("/api/v1/team/members", headers=headers)
    statuses = {row["id"]: row["today_status"] for row in listed.json()["items"]}
    assert statuses[scenario.employees["employee_a"].id] == "half-day"
    assert statuses[scenario.employees["manager_a"].id] is None
    monkeypatch.setattr(
        "app.services.roster_service.utc_now",
        lambda: datetime(2026, 10, 17, 3, tzinfo=timezone.utc),
    )
    assert all(
        row["today_status"] == "weekend"
        for row in auth_client.get("/api/v1/team/members", headers=headers).json()["items"]
    )

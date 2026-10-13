from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Connection, Engine, event, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.deps.authz import (
    AuthorizationContext,
    authorize,
    has_permission,
    is_admin,
    manages_team_of,
    scoped_employee_ids_query,
    scopes_for,
)
from app.models import Employee, Permission, Role, RolePermission, TeamManager
from app.services.authorization_service import load_permissions
from app.utils.time import utc_now
from tests.authz_support import AuthzScenario
from tests.test_auth import bearer, login_token


def context(session: Session, employee: Employee) -> AuthorizationContext:
    return AuthorizationContext(employee, session, load_permissions(session, employee.role_id))


@pytest.mark.parametrize(
    "actor,expected_scopes,admin",
    [
        ("employee_a", {"self"}, False),
        ("senior", {"self"}, False),
        ("manager_a", {"self", "team"}, False),
        ("hr", {"self", "any"}, True),
        ("c_level", {"self", "any"}, True),
    ],
)
def test_scopes_and_admin_helper_are_permission_based(
    scenario: AuthzScenario,
    seeded_session: Session,
    actor: str,
    expected_scopes: set[str],
    admin: bool,
) -> None:
    caller = context(seeded_session, scenario.employees[actor])
    assert has_permission(caller, "attendance", "read") == expected_scopes
    assert scopes_for(caller, "attendance", "read") == expected_scopes
    assert is_admin(caller) is admin


def test_own_creation_and_target_required_for_team_updates(
    scenario: AuthzScenario,
    seeded_session: Session,
) -> None:
    employee = context(seeded_session, scenario.employees["employee_a"])
    authorize(employee, "attendance", "create")
    manager = context(seeded_session, scenario.employees["manager_a"])
    with pytest.raises(AppError) as error:
        authorize(manager, "attendance", "update")
    assert error.value.status_code == 403 and error.value.code == "PERMISSION_DENIED"


def test_admin_permission_does_not_grant_unrelated_actions(
    scenario: AuthzScenario,
    seeded_session: Session,
) -> None:
    admin = context(seeded_session, scenario.employees["hr"])
    assert is_admin(admin)
    authorize(admin, "employee", "create")
    with pytest.raises(AppError) as error:
        authorize(admin, "attendance", "create", scenario.employees["employee_a"])
    assert error.value.code == "OUT_OF_SCOPE"
    with pytest.raises(AppError) as error:
        authorize(admin, "unknown", "read", scenario.employees["employee_a"])
    assert error.value.code == "PERMISSION_DENIED"
    with pytest.raises(AppError):
        scoped_employee_ids_query(admin, "unknown", "read")


def test_managed_team_check_uses_only_active_assignments(
    scenario: AuthzScenario,
    seeded_session: Session,
) -> None:
    caller = context(seeded_session, scenario.employees["manager_a"])
    assert manages_team_of(caller, scenario.employees["employee_a"])
    assert not manages_team_of(caller, scenario.employees["employee_b"])
    assert not manages_team_of(caller, scenario.employees["unassigned"])
    scenario.managers["a"].removed_at = utc_now()
    seeded_session.flush()
    assert not manages_team_of(caller, scenario.employees["employee_a"])


def test_permissions_loaded_once_for_multiple_checks_per_request(
    authz_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    db_engine: Engine,
) -> None:
    token = login_token(authz_client, scenario.employees["manager_a"], initial_password)
    queries: list[str] = []

    def track(
        _connection: Connection,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        if "FROM permissions" in statement and "JOIN role_permissions" in statement:
            queries.append(statement)

    event.listen(db_engine, "before_cursor_execute", track)
    try:
        response = authz_client.get("/api/v1/authz/cache", headers=bearer(token))
        assert response.status_code == 200
        assert response.json() == {"same_context": True, "same_permissions": True}
        assert len(queries) == 1
        assert authz_client.get("/api/v1/authz/cache", headers=bearer(token)).status_code == 200
        assert len(queries) == 2
    finally:
        event.remove(db_engine, "before_cursor_execute", track)


def test_self_only_foreign_target_is_rejected_before_target_lookup(
    authz_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    db_engine: Engine,
) -> None:
    token = login_token(authz_client, scenario.employees["employee_a"], initial_password)
    queries: list[str] = []

    def track(
        _connection: Connection,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        if "FROM employees" in statement:
            queries.append(statement)

    event.listen(db_engine, "before_cursor_execute", track)
    try:
        for target_id in (scenario.employees["employee_b"].id, 2**63):
            queries.clear()
            response = authz_client.get(
                "/api/v1/authz/attendance/target",
                headers=bearer(token),
                params={"employee_id": target_id},
            )
            assert response.status_code == 403 and response.json()["code"] == "OUT_OF_SCOPE"
            assert len(queries) == 1  # Authentication reload only, no target existence query.
    finally:
        event.remove(db_engine, "before_cursor_execute", track)


def test_pagination_and_counts_use_the_filtered_scope(
    authz_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
) -> None:
    token = login_token(authz_client, scenario.employees["manager_a"], initial_password)
    expected = sorted(scenario.team_ids("a"))
    first = authz_client.get(
        "/api/v1/team/members", headers=bearer(token), params={"page": 1, "page_size": 2}
    )
    second = authz_client.get(
        "/api/v1/team/members", headers=bearer(token), params={"page": 2, "page_size": 2}
    )
    assert first.json()["ids"] == expected[:2]
    assert second.json()["ids"] == expected[2:]
    assert first.json()["total"] == second.json()["total"] == len(expected)
    invalid = authz_client.get(
        "/api/v1/team/members", headers=bearer(token), params={"page_size": 101}
    )
    assert invalid.status_code == 422


def test_duplicate_manager_history_does_not_duplicate_list_results(
    authz_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    seeded_session: Session,
) -> None:
    manager = scenario.employees["manager_a"]
    seeded_session.add(
        TeamManager(
            team_id=scenario.teams["a"].id,
            employee_id=manager.id,
            assigned_at=utc_now() - timedelta(hours=1),
        )
    )
    seeded_session.flush()
    token = login_token(authz_client, manager, initial_password)
    response = authz_client.get("/api/v1/team/members", headers=bearer(token))
    expected = scenario.team_ids("a")
    assert response.status_code == 200 and set(response.json()["ids"]) == expected
    assert response.json()["total"] == len(response.json()["ids"]) == len(expected)


def test_custom_role_with_same_permissions_has_same_access(
    authz_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    seeded_session: Session,
) -> None:
    employee = scenario.employees["employee_a"]
    token = login_token(authz_client, employee, initial_password)
    role = Role(name="custom-label")
    seeded_session.add(role)
    seeded_session.flush()
    hr = scenario.employees["hr"]
    permissions = list(
        seeded_session.scalars(
            select(RolePermission.permission_id).where(
                RolePermission.role_id == hr.role_id,
            )
        )
    )
    seeded_session.add_all(
        RolePermission(role_id=role.id, permission_id=permission_id)
        for permission_id in permissions
    )
    employee.role_id = role.id
    seeded_session.flush()
    assert authz_client.get("/api/v1/authz/admin-create", headers=bearer(token)).status_code == 200
    listed = authz_client.get("/api/v1/authz/attendance", headers=bearer(token))
    assert set(listed.json()["ids"]) == scenario.ids()
    assert is_admin(context(seeded_session, employee))
    assert (
        authz_client.get("/api/v1/me", headers=bearer(token)).json()["role"]["name"]
        == "custom-label"
    )


def test_active_manager_row_without_permission_does_not_grant_team_access(
    authz_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    seeded_session: Session,
) -> None:
    employee = scenario.employees["employee_a"]
    seeded_session.add(TeamManager(team_id=scenario.teams["b"].id, employee_id=employee.id))
    seeded_session.flush()
    token = login_token(authz_client, employee, initial_password)
    response = authz_client.get(
        "/api/v1/authz/attendance/target",
        headers=bearer(token),
        params={"employee_id": scenario.employees["employee_b"].id},
    )
    assert response.status_code == 403
    assert authz_client.get("/api/v1/authz/attendance", headers=bearer(token)).json()["ids"] == [
        employee.id
    ]


def test_self_scope_cannot_satisfy_team_only_endpoint(
    authz_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    seeded_session: Session,
) -> None:
    employee = scenario.employees["employee_a"]
    permission = Permission(
        code="employee.read.self", resource="employee", action="read", scope="self"
    )
    seeded_session.add(permission)
    seeded_session.flush()
    seeded_session.add(RolePermission(role_id=employee.role_id, permission_id=permission.id))
    seeded_session.flush()
    token = login_token(authz_client, employee, initial_password)
    response = authz_client.get("/api/v1/team/members", headers=bearer(token))
    assert response.status_code == 403 and response.json()["code"] == "PERMISSION_DENIED"


def test_generic_scope_preserves_inactive_employee_history(
    authz_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    seeded_session: Session,
) -> None:
    scenario.employees["employee_a"].is_active = False
    seeded_session.flush()
    token = login_token(authz_client, scenario.employees["manager_a"], initial_password)
    listed = authz_client.get("/api/v1/authz/attendance", headers=bearer(token))
    assert scenario.employees["employee_a"].id in listed.json()["ids"]


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/team/members",
        "/api/v1/authz/attendance",
        "/api/v1/authz/admin-create",
        "/api/v1/authz/cache",
    ],
)
def test_authorization_probes_require_authentication(authz_client: TestClient, path: str) -> None:
    assert authz_client.get(path).status_code == 401


def test_production_app_does_not_publish_authz_probes(settings: Settings) -> None:
    from app.main import create_app

    paths = set(create_app(settings).openapi()["paths"])
    assert "/api/v1/team/members" not in paths
    assert not any(path.startswith("/api/v1/authz/") for path in paths)


@pytest.mark.parametrize(
    "code,scope",
    [
        ("unrelated.read.any", "any"),
        ("employee.create.any", "self"),
    ],
)
def test_inconsistent_permission_metadata_cannot_grant_access(
    authz_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    seeded_session: Session,
    code: str,
    scope: str,
) -> None:
    employee = scenario.employees["employee_a"]
    # The second case deliberately corrupts metadata for an existing permission.
    permission = seeded_session.execute(
        select(Permission).where(Permission.code == code)
    ).scalar_one_or_none()
    if permission is None:
        permission = Permission(code=code, resource="employee", action="create", scope=scope)
        seeded_session.add(permission)
    else:
        permission.scope = scope
    seeded_session.flush()
    seeded_session.add(RolePermission(role_id=employee.role_id, permission_id=permission.id))
    seeded_session.flush()
    caller = context(seeded_session, employee)
    assert has_permission(caller, "employee", "create") == set()
    assert not is_admin(caller)
    token = login_token(authz_client, employee, initial_password)
    assert authz_client.get("/api/v1/authz/admin-create", headers=bearer(token)).status_code == 403
    assert code not in authz_client.get("/api/v1/me", headers=bearer(token)).json()["permissions"]

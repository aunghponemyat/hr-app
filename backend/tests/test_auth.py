from datetime import timedelta

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import decode_token, token_digest, verify_password
from app.models import Employee, Permission, RefreshSession, RolePermission
from app.utils.time import utc_now

LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
CHANGE = "/api/v1/auth/change-password"
LOGOUT = "/api/v1/auth/logout"


def login_token(client: TestClient, employee: Employee, password: SecretStr) -> str:
    response = client.post(
        LOGIN, data={"username": employee.employee_id, "password": password.get_secret_value()}
    )
    assert response.status_code == 200, response.json().get("code")
    return str(response.json()["access_token"])


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_login_sets_cookie_claims_and_last_login(
    auth_client: TestClient,
    auth_employee: Employee,
    initial_password: SecretStr,
    auth_settings: Settings,
    seeded_session: Session,
) -> None:
    response = auth_client.post(
        LOGIN,
        data={
            "username": auth_employee.employee_id,
            "password": initial_password.get_secret_value(),
            "grant_type": "password",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer" and data["expires_in"] == 1800
    assert data["pwd_change_required"] is True
    assert "refresh_token" not in data
    claims = decode_token(data["access_token"], "access", auth_settings)
    assert claims.sub == str(auth_employee.id)
    assert claims.employee_id == auth_employee.employee_id
    assert claims.role == "employee" and claims.pwd_change_required is True
    assert claims.exp - claims.iat == 1800
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/api/v1/auth" in cookie
    assert "Max-Age=604800" in cookie and "Secure" not in cookie
    assert response.headers["cache-control"] == "no-store"
    assert auth_employee.last_login_at is not None
    assert auth_employee.failed_login_count == 0
    refresh_token = str(auth_client.cookies.get("refresh_token"))
    refresh_claims = decode_token(refresh_token, "refresh", auth_settings)
    persisted = seeded_session.get(RefreshSession, refresh_claims.sid)
    assert persisted is not None and persisted.token_hash == token_digest(refresh_token)
    assert persisted.token_hash != refresh_token


def test_login_failures_are_generic(
    auth_client: TestClient,
    auth_employee: Employee,
    initial_password: SecretStr,
    seeded_session: Session,
) -> None:
    wrong_id = auth_client.post(
        LOGIN, data={"username": "MISSING", "password": initial_password.get_secret_value()}
    )
    wrong_password = auth_client.post(
        LOGIN, data={"username": auth_employee.employee_id, "password": "wrong"}
    )
    auth_employee.is_active = False
    seeded_session.flush()
    inactive = auth_client.post(
        LOGIN,
        data={
            "username": auth_employee.employee_id,
            "password": initial_password.get_secret_value(),
        },
    )
    assert wrong_id.status_code == wrong_password.status_code == inactive.status_code == 401
    assert wrong_id.json() == wrong_password.json() == inactive.json()
    assert wrong_id.json()["code"] == "INVALID_CREDENTIALS"


def test_lockout_persists_failures_and_blocks_correct_password(
    auth_client: TestClient,
    auth_employee: Employee,
    initial_password: SecretStr,
    seeded_session: Session,
    auth_settings: Settings,
) -> None:
    for number in range(1, auth_settings.max_failed_logins + 1):
        response = auth_client.post(
            LOGIN, data={"username": auth_employee.employee_id, "password": "wrong"}
        )
        assert response.status_code == (429 if number == auth_settings.max_failed_logins else 401)
        seeded_session.refresh(auth_employee)
        assert auth_employee.failed_login_count == number
    locked = auth_client.post(
        LOGIN,
        data={
            "username": auth_employee.employee_id,
            "password": initial_password.get_secret_value(),
        },
    )
    assert locked.status_code == 429 and locked.json()["code"] == "ACCOUNT_LOCKED"
    assert int(locked.headers["retry-after"]) > 0
    assert auth_employee.locked_until is not None


def test_expired_lockout_resets_on_success(
    auth_client: TestClient,
    auth_employee: Employee,
    initial_password: SecretStr,
    seeded_session: Session,
) -> None:
    auth_employee.failed_login_count = 5
    auth_employee.locked_until = utc_now() - timedelta(minutes=1)
    seeded_session.flush()
    login_token(auth_client, auth_employee, initial_password)
    assert auth_employee.failed_login_count == 0 and auth_employee.locked_until is None


def test_password_gate_and_change_revokes_old_tokens(
    auth_client: TestClient,
    auth_employee: Employee,
    initial_password: SecretStr,
    auth_settings: Settings,
) -> None:
    old_access = login_token(auth_client, auth_employee, initial_password)
    old_refresh = str(auth_client.cookies.get("refresh_token"))
    own = auth_client.get("/api/v1/me", headers=bearer(old_access))
    assert own.status_code == 200 and own.json()["must_change_password"] is True
    assert "password_hash" not in own.text and "locked_until" not in own.text
    blocked = auth_client.get("/api/v1/test-protected", headers=bearer(old_access))
    assert blocked.status_code == 403 and blocked.json()["code"] == "PASSWORD_CHANGE_REQUIRED"
    response = auth_client.post(
        CHANGE,
        headers=bearer(old_access),
        json={
            "current_password": initial_password.get_secret_value(),
            "new_password": "Replacement123",
        },
    )
    assert response.status_code == 200 and response.json()["pwd_change_required"] is False
    new_access = str(response.json()["access_token"])
    assert auth_client.get("/api/v1/test-protected", headers=bearer(new_access)).status_code == 200
    assert auth_client.get("/api/v1/me", headers=bearer(old_access)).status_code == 401
    auth_client.cookies.clear()
    replay = auth_client.post(REFRESH, headers={"Cookie": f"refresh_token={old_refresh}"})
    assert replay.status_code == 401
    assert auth_employee.password_changed_at is not None and not auth_employee.must_change_password
    assert verify_password("Replacement123", auth_employee.password_hash)[0]
    assert decode_token(new_access, "access", auth_settings).pwd_changed_at is not None


@pytest.mark.parametrize("new_password", ["short1", "12345678", "abcdefgh", "InitialPass123"])
def test_password_policy_is_enforced(
    auth_client: TestClient, auth_employee: Employee, initial_password: SecretStr, new_password: str
) -> None:
    token = login_token(auth_client, auth_employee, initial_password)
    response = auth_client.post(
        CHANGE,
        headers=bearer(token),
        json={
            "current_password": initial_password.get_secret_value(),
            "new_password": new_password,
        },
    )
    assert response.status_code == 422
    assert (
        new_password not in response.text
        and initial_password.get_secret_value() not in response.text
    )


def test_password_change_rejects_wrong_current_password(
    auth_client: TestClient, auth_employee: Employee, initial_password: SecretStr
) -> None:
    token = login_token(auth_client, auth_employee, initial_password)
    response = auth_client.post(
        CHANGE,
        headers=bearer(token),
        json={"current_password": "wrong", "new_password": "Replacement123"},
    )
    assert response.status_code == 401 and response.json()["code"] == "INVALID_CREDENTIALS"
    assert auth_employee.must_change_password


def test_refresh_rotates_and_rejects_replay(
    auth_client: TestClient, auth_employee: Employee, initial_password: SecretStr
) -> None:
    access = login_token(auth_client, auth_employee, initial_password)
    original = str(auth_client.cookies.get("refresh_token"))
    response = auth_client.post(REFRESH)
    assert response.status_code == 200
    rotated = str(auth_client.cookies.get("refresh_token"))
    assert rotated != original and response.json()["access_token"] != access
    auth_client.cookies.clear()
    replay = auth_client.post(REFRESH, headers={"Cookie": f"refresh_token={original}"})
    assert replay.status_code == 401
    assert (
        auth_client.post(REFRESH, headers={"Cookie": f"refresh_token={rotated}"}).status_code == 200
    )


def test_logout_clears_cookie_and_revokes_session(
    auth_client: TestClient, auth_employee: Employee, initial_password: SecretStr
) -> None:
    token = login_token(auth_client, auth_employee, initial_password)
    refresh_token = str(auth_client.cookies.get("refresh_token"))
    response = auth_client.post(LOGOUT, headers=bearer(token))
    assert response.status_code == 200 and response.json() == {"message": "Logged out."}
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert auth_client.get("/api/v1/me", headers=bearer(token)).status_code == 401
    auth_client.cookies.clear()
    assert (
        auth_client.post(REFRESH, headers={"Cookie": f"refresh_token={refresh_token}"}).status_code
        == 401
    )


@pytest.mark.parametrize(
    "path,method", [("/api/v1/me", "get"), (LOGOUT, "post"), (CHANGE, "post"), (REFRESH, "post")]
)
def test_authentication_required(auth_client: TestClient, path: str, method: str) -> None:
    response = auth_client.request(
        method,
        path,
        json={"current_password": "InitialPass123", "new_password": "Replacement123"}
        if path == CHANGE
        else None,
    )
    assert response.status_code == 401


def test_inactive_employee_rejected_on_access_and_refresh(
    auth_client: TestClient,
    auth_employee: Employee,
    initial_password: SecretStr,
    seeded_session: Session,
) -> None:
    token = login_token(auth_client, auth_employee, initial_password)
    auth_employee.is_active = False
    seeded_session.flush()
    assert auth_client.get("/api/v1/me", headers=bearer(token)).status_code == 401
    assert auth_client.post(REFRESH).status_code == 401


@pytest.mark.parametrize(
    "changes",
    [
        {"type": "refresh"},
        {"exp": 1},
        {"iat": 9999999999},
        {"sub": "not-an-id"},
        {"sid": 0},
        {"pwd_changed_at": "old-password-state"},
    ],
)
def test_invalid_token_claims_rejected(
    auth_client: TestClient,
    auth_employee: Employee,
    initial_password: SecretStr,
    auth_settings: Settings,
    changes: dict[str, object],
) -> None:
    token = login_token(auth_client, auth_employee, initial_password)
    key = auth_settings.jwt_secret_key.get_secret_value()
    payload = jwt.decode(token, key, algorithms=["HS256"])
    payload.update(changes)
    invalid = jwt.encode(payload, key, algorithm="HS256")
    response = auth_client.get("/api/v1/me", headers=bearer(invalid))
    assert response.status_code == 401 and response.json()["code"] == "INVALID_TOKEN"
    assert response.headers["www-authenticate"] == "Bearer"


def test_bad_signature_rejected(
    auth_client: TestClient,
    auth_employee: Employee,
    initial_password: SecretStr,
    auth_settings: Settings,
) -> None:
    token = login_token(auth_client, auth_employee, initial_password)
    payload = decode_token(token, "access", auth_settings).model_dump()
    invalid = jwt.encode(payload, "unrelated-signing-key-32-characters", algorithm="HS256")
    assert auth_client.get("/api/v1/me", headers=bearer(invalid)).status_code == 401


def test_me_checks_permission_from_database(
    auth_client: TestClient,
    auth_employee: Employee,
    initial_password: SecretStr,
    seeded_session: Session,
) -> None:
    token = login_token(auth_client, auth_employee, initial_password)
    permission_id = seeded_session.execute(
        select(Permission.id).where(Permission.code == "profile.read.self")
    ).scalar_one()
    seeded_session.execute(
        delete(RolePermission).where(
            RolePermission.role_id == auth_employee.role_id,
            RolePermission.permission_id == permission_id,
        )
    )
    seeded_session.expire_all()
    response = auth_client.get("/api/v1/me", headers=bearer(token))
    assert response.status_code == 403 and response.json()["code"] == "PERMISSION_DENIED"


def test_untrusted_origin_blocked_for_auth_mutations(
    auth_client: TestClient, auth_employee: Employee, initial_password: SecretStr
) -> None:
    login_token(auth_client, auth_employee, initial_password)
    response = auth_client.post(REFRESH, headers={"Origin": "https://untrusted.example"})
    assert response.status_code == 403 and response.json()["code"] == "FORBIDDEN_ORIGIN"
    assert auth_client.post(REFRESH, headers={"Origin": "http://localhost:5173"}).status_code == 200


def test_secure_cookie_when_configured(
    auth_app: FastAPI, auth_settings: Settings, auth_employee: Employee, initial_password: SecretStr
) -> None:
    auth_settings.cookie_secure = True
    with TestClient(auth_app, base_url="https://testserver") as client:
        response = client.post(
            LOGIN,
            data={
                "username": auth_employee.employee_id,
                "password": initial_password.get_secret_value(),
            },
        )
        assert response.status_code == 200 and "Secure" in response.headers["set-cookie"]
        assert client.post(REFRESH).status_code == 200

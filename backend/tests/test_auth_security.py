import logging
from datetime import timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import decode_token
from app.models import Employee, RefreshSession
from app.services.login_limiter import LoginRateLimiter
from app.utils.time import utc_now
from tests.test_auth import LOGIN, REFRESH, bearer, login_token


def test_ip_rate_limit_cannot_be_bypassed_with_forwarded_header(
    auth_client: TestClient, auth_settings: Settings
) -> None:
    auth_settings.login_rate_limit_ip = 2
    for number in range(2):
        response = auth_client.post(
            LOGIN, data={"username": f"MISSING{number}", "password": "wrong"}
        )
        assert response.status_code == 401
    denied = auth_client.post(
        LOGIN,
        headers={"X-Forwarded-For": "different-ip"},
        data={"username": "ANOTHER", "password": "wrong"},
    )
    assert denied.status_code == 429 and denied.json()["code"] == "RATE_LIMITED"
    assert int(denied.headers["retry-after"]) > 0


def test_employee_rate_limit_across_ips_and_window_expiration(auth_settings: Settings) -> None:
    auth_settings.login_rate_limit_employee = 2
    now = [100.0]
    limiter = LoginRateLimiter(auth_settings, lambda: now[0])
    limiter.check("ip1", "EMP0001")
    limiter.check("ip2", "emp0001")
    with pytest.raises(AppError) as error:
        limiter.check("ip3", "EMP0001")
    assert error.value.code == "RATE_LIMITED"
    assert not any("EMP0001" in key or "ip1" in key for key in limiter.buckets)
    now[0] += auth_settings.login_rate_limit_window_seconds
    limiter.check("ip3", "EMP0001")


def test_login_rehashes_old_argon2_parameters(
    auth_client: TestClient,
    auth_employee: Employee,
    initial_password: SecretStr,
    seeded_session: Session,
) -> None:
    old_hash = PasswordHash((Argon2Hasher(time_cost=1, memory_cost=8192),)).hash(
        initial_password.get_secret_value()
    )
    auth_employee.password_hash = old_hash
    seeded_session.flush()
    login_token(auth_client, auth_employee, initial_password)
    assert auth_employee.password_hash != old_hash


def test_refresh_rejects_access_token_cookie(
    auth_client: TestClient, auth_employee: Employee, initial_password: SecretStr
) -> None:
    token = login_token(auth_client, auth_employee, initial_password)
    auth_client.cookies.clear()
    assert (
        auth_client.post(REFRESH, headers={"Cookie": f"refresh_token={token}"}).status_code == 401
    )


def test_missing_required_claim_rejected(
    auth_client: TestClient,
    auth_employee: Employee,
    initial_password: SecretStr,
    auth_settings: Settings,
) -> None:
    token = login_token(auth_client, auth_employee, initial_password)
    claims = decode_token(token, "access", auth_settings).model_dump()
    del claims["exp"]
    invalid = jwt.encode(claims, auth_settings.jwt_secret_key.get_secret_value(), algorithm="HS256")
    assert auth_client.get("/api/v1/me", headers=bearer(invalid)).status_code == 401


def test_wrong_algorithm_rejected(
    auth_client: TestClient,
    auth_employee: Employee,
    initial_password: SecretStr,
    auth_settings: Settings,
) -> None:
    token = login_token(auth_client, auth_employee, initial_password)
    claims = decode_token(token, "access", auth_settings).model_dump()
    invalid = jwt.encode(claims, auth_settings.jwt_secret_key.get_secret_value(), algorithm="HS512")
    assert auth_client.get("/api/v1/me", headers=bearer(invalid)).status_code == 401


def test_session_expiration_enforced(
    auth_client: TestClient,
    auth_employee: Employee,
    initial_password: SecretStr,
    auth_settings: Settings,
    seeded_session: Session,
) -> None:
    token = login_token(auth_client, auth_employee, initial_password)
    claims = decode_token(token, "access", auth_settings)
    record = seeded_session.get(RefreshSession, claims.sid)
    assert record is not None
    record.expires_at = utc_now() - timedelta(seconds=1)
    seeded_session.flush()
    assert auth_client.get("/api/v1/me", headers=bearer(token)).status_code == 401
    assert auth_client.post(REFRESH).status_code == 401


def test_auth_secrets_are_not_logged(
    auth_client: TestClient,
    auth_employee: Employee,
    initial_password: SecretStr,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG):
        token = login_token(auth_client, auth_employee, initial_password)
        cookie = str(auth_client.cookies.get("refresh_token"))
        auth_client.get("/api/v1/me", headers=bearer(token))
    assert initial_password.get_secret_value() not in caplog.text
    assert token not in caplog.text and cookie not in caplog.text


def test_unconfigured_jwt_secret_fails_closed(
    auth_client: TestClient,
    auth_employee: Employee,
    initial_password: SecretStr,
    auth_settings: Settings,
) -> None:
    auth_settings.jwt_secret_key = SecretStr("change-me-long-random")
    response = auth_client.post(
        LOGIN,
        data={
            "username": auth_employee.employee_id,
            "password": initial_password.get_secret_value(),
        },
    )
    assert response.status_code == 503 and response.json()["code"] == "AUTH_NOT_CONFIGURED"


def test_password_gate_uses_database_not_token_flag(
    auth_client: TestClient,
    auth_employee: Employee,
    initial_password: SecretStr,
    auth_settings: Settings,
) -> None:
    token = login_token(auth_client, auth_employee, initial_password)
    claims = decode_token(token, "access", auth_settings).model_dump()
    claims["pwd_change_required"] = False
    signed = jwt.encode(claims, auth_settings.jwt_secret_key.get_secret_value(), algorithm="HS256")
    response = auth_client.get("/api/v1/test-protected", headers=bearer(signed))
    assert response.status_code == 403 and response.json()["code"] == "PASSWORD_CHANGE_REQUIRED"

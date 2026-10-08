import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import Field

from app.core.config import Settings
from app.core.errors import AppError
from app.main import create_app
from app.schemas.common import RequestSchema


class SensitiveRequest(RequestSchema):
    password: str = Field(min_length=8)


def test_application_permission_error_has_uniform_body(settings: Settings) -> None:
    app = create_app(settings)

    @app.get("/test-denied")
    def denied() -> None:
        raise AppError(403, "OUT_OF_SCOPE", "Employee is outside your team.")

    with TestClient(app) as client:
        response = client.get("/test-denied")
    assert response.status_code == 403
    assert response.json() == {
        "code": "OUT_OF_SCOPE",
        "message": "Employee is outside your team.",
        "details": None,
    }


def test_unknown_route_and_wrong_method_are_uniform(client: TestClient) -> None:
    assert client.get("/missing").json()["code"] == "NOT_FOUND"
    assert client.post("/healthz").json()["code"] == "METHOD_NOT_ALLOWED"


def add_validation_route(app: FastAPI) -> None:
    @app.post("/test-validation")
    def validate(payload: SensitiveRequest) -> dict[str, bool]:
        return {"accepted": bool(payload.password)}


def test_validation_does_not_echo_passwords_or_unknown_tokens(settings: Settings) -> None:
    app = create_app(settings)
    add_validation_route(app)
    with TestClient(app) as client:
        response = client.post(
            "/test-validation", json={"password": "abc", "token": "secret-token-value"}
        )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert "secret-token-value" not in response.text
    assert "abc" not in response.text


def test_unhandled_errors_are_redacted_and_correlated(
    settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    app = create_app(settings)

    @app.get("/test-error")
    def fail() -> None:
        raise RuntimeError("password=super-secret-value")

    with caplog.at_level(logging.ERROR), TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/test-error")
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert "super-secret-value" not in response.text
    assert "super-secret-value" not in caplog.text
    assert response.headers["x-request-id"] in caplog.text


def test_cors_permits_only_configured_origins(client: TestClient) -> None:
    allowed = client.get("/healthz", headers={"Origin": "http://localhost:5173"})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert allowed.headers["access-control-allow-credentials"] == "true"
    denied = client.get("/healthz", headers={"Origin": "https://untrusted.example"})
    assert "access-control-allow-origin" not in denied.headers

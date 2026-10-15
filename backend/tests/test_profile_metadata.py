from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings
from tests.authz_support import AuthzScenario
from tests.test_auth import bearer, login_token


def test_profile_exposes_server_office_configuration(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    auth_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth_settings.app_timezone = "Pacific/Honolulu"
    auth_settings.max_report_range_days = 31
    monkeypatch.setattr(
        "app.services.profile_service.utc_now",
        lambda: datetime(2026, 10, 15, 2, tzinfo=timezone.utc),
    )
    token = login_token(auth_client, scenario.employees["employee_a"], initial_password)
    expected = {"timezone": "Pacific/Honolulu", "today": "2026-10-14", "max_report_range_days": 31}
    for response in (
        auth_client.get("/api/v1/me", headers=bearer(token)),
        auth_client.patch("/api/v1/me", headers=bearer(token), json={"display_name": "Ada"}),
    ):
        assert response.status_code == 200
        assert response.json()["app"] == expected
    assert auth_client.get("/api/v1/me").status_code == 401
    assert (
        auth_client.patch("/api/v1/me", headers=bearer(token), json={"app": expected}).status_code
        == 422
    )

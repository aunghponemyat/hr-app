from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_health_is_public_and_does_not_require_database(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert len(response.headers["x-request-id"]) == 32


def test_health_remains_public_with_invalid_authorization(client: TestClient) -> None:
    response = client.get("/healthz", headers={"Authorization": "Bearer invalid"})
    assert response.status_code == 200


def test_health_schema_is_documented(client: TestClient) -> None:
    document = client.get("/openapi.json").json()
    assert document["paths"]["/healthz"]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ]["$ref"].endswith("HealthResponse")


def test_docs_disabled_in_production() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        jwt_secret_key="a" * 32,
        cookie_secure=True,
        cors_origins="https://hr.example.com",
    )
    with TestClient(create_app(settings)) as client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert client.get(path).status_code == 404
        assert client.get("/healthz").status_code == 200

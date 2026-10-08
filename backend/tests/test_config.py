import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


def test_comma_separated_environment_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKING_WEEKDAYS", "0, 1, 2, 3, 4")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173, https://hr.example.com")
    monkeypatch.setenv("MAX_FAILED_LOGINS", "8")
    settings = Settings(_env_file=None)
    assert settings.working_weekday_numbers == frozenset({0, 1, 2, 3, 4})
    assert settings.allowed_origins == ["http://localhost:5173", "https://hr.example.com"]
    assert settings.max_failed_logins == 8


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("working_weekdays", ""),
        ("working_weekdays", "0,7"),
        ("working_weekdays", "1,1"),
        ("working_weekdays", "Monday"),
        ("app_timezone", "Unknown/Zone"),
        ("cors_origins", "*"),
        ("cors_origins", "https://example.com/path"),
        ("cors_origins", "https://user:password@example.com"),
        ("database_url", "sqlite:///test.db"),
        ("max_report_range_days", "367"),
        ("max_failed_logins", "0"),
    ],
)
def test_invalid_configuration_rejected(
    monkeypatch: pytest.MonkeyPatch, field: str, value: str
) -> None:
    monkeypatch.setenv(field.upper(), value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_production_rejects_insecure_defaults() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production")


def test_settings_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    try:
        assert get_settings() is get_settings()
    finally:
        get_settings.cache_clear()


def test_settings_repr_hides_credentials() -> None:
    settings = Settings(_env_file=None, jwt_secret_key="private-token-secret")
    assert "private-token-secret" not in repr(settings)
    assert "hr_pass" not in repr(settings)

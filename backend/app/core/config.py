from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: SecretStr = SecretStr("mysql+pymysql://hr_user:hr_pass@127.0.0.1:3306/hr_app")
    test_database_url: SecretStr = SecretStr(
        "mysql+pymysql://hr_test:hr_test_pass@127.0.0.1:3307/hr_app_test"
    )
    jwt_secret_key: SecretStr = SecretStr("")
    jwt_algorithm: Literal["HS256"] = "HS256"
    access_token_expire_minutes: int = Field(default=30, gt=0)
    refresh_token_expire_days: int = Field(default=7, gt=0)
    cookie_secure: bool = False
    max_failed_logins: int = Field(default=5, gt=0)
    lockout_minutes: int = Field(default=15, gt=0)
    app_env: Literal["development", "test", "production"] = "development"
    app_timezone: str = "Asia/Bangkok"
    working_weekdays: str = "0,1,2,3,4"
    half_day_threshold_hours: float = Field(default=4, gt=0, le=24)
    max_gps_accuracy_m: float = Field(default=100, gt=0)
    max_report_range_days: int = Field(default=366, gt=0, le=366)
    leave_max_days_per_request: int = Field(default=30, gt=0, le=99)
    leave_backdate_days: int = Field(default=7, ge=0)
    employee_id_prefix: str = Field(default="EMP", min_length=1, max_length=19)
    employee_id_pad: int = Field(default=4, ge=1, le=19)
    cors_origins: str = "http://localhost:5173"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
        allow_inf_nan=False,
    )

    @field_validator("database_url", "test_database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        if urlsplit(value.get_secret_value()).scheme != "mysql+pymysql":
            raise ValueError("Database URLs must use mysql+pymysql.")
        return value

    @field_validator("app_timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("APP_TIMEZONE must be a valid IANA timezone.") from exc
        return value

    @field_validator("working_weekdays")
    @classmethod
    def validate_weekdays(cls, value: str) -> str:
        days = [int(day.strip()) for day in value.split(",")]
        if not days or any(day < 0 or day > 6 for day in days) or len(set(days)) != len(days):
            raise ValueError("WORKING_WEEKDAYS must contain unique weekday numbers from 0 to 6.")
        return ",".join(str(day) for day in sorted(days))

    @field_validator("cors_origins")
    @classmethod
    def validate_origins(cls, value: str) -> str:
        origins = [origin.strip() for origin in value.split(",")]
        for origin in origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or "*" in origin
                or parsed.username
                or parsed.password
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    "CORS_ORIGINS must contain explicit HTTP(S) origins without paths."
                )
        return ",".join(origins)

    @model_validator(mode="after")
    def validate_production(self) -> "Settings":
        if len(self.employee_id_prefix) + self.employee_id_pad > 20:
            raise ValueError("Employee ID prefix and padding must fit within 20 characters.")
        if self.app_env == "production":
            secret = self.jwt_secret_key.get_secret_value()
            if len(secret) < 32 or secret.startswith("change-me"):
                raise ValueError(
                    "Production requires a random JWT secret of at least 32 characters."
                )
            if not self.cookie_secure:
                raise ValueError("Production requires COOKIE_SECURE=true.")
            if any(urlsplit(origin).scheme != "https" for origin in self.allowed_origins):
                raise ValueError("Production CORS origins must use HTTPS.")
        return self

    @property
    def allowed_origins(self) -> list[str]:
        return self.cors_origins.split(",")

    @property
    def working_weekday_numbers(self) -> frozenset[int]:
        return frozenset(int(day) for day in self.working_weekdays.split(","))


@lru_cache
def get_settings() -> Settings:
    return Settings()

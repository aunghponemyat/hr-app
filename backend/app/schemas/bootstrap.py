from typing import Literal

from pydantic import Field, SecretStr, field_validator

from app.core.security import validate_password
from app.schemas.common import RequestSchema


class AdminCreateRequest(RequestSchema):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    role: Literal["hr", "c_level"] = "hr"
    employee_id: str | None = Field(default=None, min_length=1, max_length=20)
    password: SecretStr = Field(min_length=8, max_length=1024)
    force: bool = False

    @field_validator("first_name", "last_name", "employee_id")
    @classmethod
    def nonblank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value or any(ord(character) < 32 for character in value):
            raise ValueError(
                "Names and employee IDs must not be blank or contain control characters."
            )
        return value

    @field_validator("password")
    @classmethod
    def password_policy(cls, value: SecretStr) -> SecretStr:
        validate_password(value.get_secret_value())
        return value

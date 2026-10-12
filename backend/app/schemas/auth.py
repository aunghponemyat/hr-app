from typing import Literal

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator

from app.core.security import validate_password
from app.schemas.common import RequestSchema


class LoginRequest(RequestSchema):
    username: str = Field(min_length=1, max_length=20)
    password: SecretStr = Field(min_length=1, max_length=1024)
    grant_type: Literal["password"] | None = None
    scope: str = ""
    client_id: str | None = None
    client_secret: SecretStr | None = None


class ChangePasswordRequest(RequestSchema):
    current_password: SecretStr = Field(min_length=1, max_length=1024)
    new_password: SecretStr = Field(
        min_length=8,
        max_length=1024,
        description=(
            "8–1024 characters, containing letters and digits; "
            "must differ from the current password."
        ),
    )

    @field_validator("new_password")
    @classmethod
    def check_policy(cls, value: SecretStr) -> SecretStr:
        validate_password(value.get_secret_value())
        return value

    @model_validator(mode="after")
    def check_different(self) -> "ChangePasswordRequest":
        if self.current_password == self.new_password:
            raise ValueError("New password must differ from the current password.")
        return self


class TokenResponse(BaseModel):
    access_token: str = Field(repr=False)
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    pwd_change_required: bool


class MessageResponse(BaseModel):
    message: str


class RoleSummary(BaseModel):
    id: int
    name: str


class TeamSummary(BaseModel):
    id: int
    name: str


class ProfileResponse(BaseModel):
    id: int
    employee_id: str
    first_name: str
    last_name: str
    display_name: str | None
    position: str | None
    department: str | None
    role: RoleSummary
    team: TeamSummary | None
    permissions: list[str]
    must_change_password: bool

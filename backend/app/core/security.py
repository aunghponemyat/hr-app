import hashlib
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Literal
from uuid import uuid4

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.core.config import Settings
from app.core.errors import AppError
from app.models import Employee


class TokenClaims(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)
    sub: str = Field(pattern=r"^[1-9][0-9]{0,19}$")
    employee_id: str
    role: str
    pwd_change_required: bool
    type: Literal["access", "refresh"]
    exp: int
    iat: int
    jti: str = Field(pattern=r"^[a-f0-9]{32}$")
    sid: int = Field(gt=0, le=2**64 - 1)
    pwd_changed_at: str | None

    @model_validator(mode="after")
    def validate_claims(self) -> "TokenClaims":
        if int(self.sub) > 2**64 - 1 or self.exp <= self.iat:
            raise ValueError("Invalid token claims.")
        return self


@lru_cache
def password_hasher() -> PasswordHash:
    return PasswordHash.recommended()


@lru_cache
def dummy_password_hash() -> str:
    return password_hasher().hash(uuid4().hex)


def validate_password(password: str) -> str:
    if (
        not 8 <= len(password) <= 1024
        or not any(character.isalpha() for character in password)
        or not any(character.isdigit() for character in password)
    ):
        raise ValueError("Password must be 8–1024 characters and include letters and digits.")
    return password


def hash_password(password: str) -> str:
    return password_hasher().hash(validate_password(password))


def verify_password(password: str, stored_hash: str) -> tuple[bool, str | None]:
    try:
        return password_hasher().verify_and_update(password, stored_hash)
    except (UnknownHashError, ValueError):
        return False, None


def signing_key(settings: Settings) -> str:
    key = settings.jwt_secret_key.get_secret_value()
    if len(key) < 32 or key.startswith("change-me"):
        raise AppError(
            503, "AUTH_NOT_CONFIGURED", "Configure a random JWT secret before signing in."
        )
    return key


def password_stamp(employee: Employee) -> str | None:
    return employee.password_changed_at.isoformat() if employee.password_changed_at else None


def create_token(
    employee: Employee,
    session_id: int,
    token_type: Literal["access", "refresh"],
    settings: Settings,
    now: datetime,
) -> str:
    duration = (
        timedelta(minutes=settings.access_token_expire_minutes)
        if token_type == "access"
        else timedelta(days=settings.refresh_token_expire_days)
    )
    claims = TokenClaims(
        sub=str(employee.id),
        employee_id=employee.employee_id,
        role=employee.role.name,
        pwd_change_required=employee.must_change_password,
        type=token_type,
        exp=int((now + duration).timestamp()),
        iat=int(now.timestamp()),
        jti=uuid4().hex,
        sid=session_id,
        pwd_changed_at=password_stamp(employee),
    )
    return jwt.encode(claims.model_dump(), signing_key(settings), algorithm=settings.jwt_algorithm)


def decode_token(
    token: str, token_type: Literal["access", "refresh"], settings: Settings
) -> TokenClaims:
    try:
        payload = jwt.decode(
            token,
            signing_key(settings),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp", "iat", "type", "sid", "jti"]},
        )
        claims = TokenClaims.model_validate(payload)
        if claims.type != token_type:
            raise ValueError("Invalid token type.")
        return claims
    except (jwt.InvalidTokenError, ValidationError, ValueError) as exc:
        raise AppError(
            401,
            "INVALID_TOKEN",
            "Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

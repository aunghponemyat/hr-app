from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.errors import AppError
from app.models import Employee
from app.services.auth_service import authenticate

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)
DatabaseSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]
BearerToken = Annotated[str | None, Depends(oauth2_scheme)]


def get_current_employee(
    session: DatabaseSession, settings: AppSettings, token: BearerToken
) -> Employee:
    if not token:
        raise AppError(
            401,
            "UNAUTHENTICATED",
            "Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return authenticate(session, token, settings)


CurrentEmployee = Annotated[Employee, Depends(get_current_employee)]


def require_password_changed(employee: CurrentEmployee) -> Employee:
    if employee.must_change_password:
        raise AppError(403, "PASSWORD_CHANGE_REQUIRED", "Change your password before continuing.")
    return employee


def enforce_auth_origin(request: Request, settings: AppSettings) -> None:
    origin = request.headers.get("origin")
    if (
        origin
        and origin not in settings.allowed_origins
        and origin != str(request.base_url).rstrip("/")
    ):
        raise AppError(403, "FORBIDDEN_ORIGIN", "Request origin is not allowed.")
    if not origin and request.headers.get("sec-fetch-site") == "cross-site":
        raise AppError(403, "FORBIDDEN_ORIGIN", "Request origin is not allowed.")

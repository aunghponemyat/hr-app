from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Form, Request, Response

from app.deps.auth import (
    AppSettings,
    BearerToken,
    CurrentEmployee,
    DatabaseSession,
    enforce_auth_origin,
)
from app.schemas.auth import ChangePasswordRequest, LoginRequest, MessageResponse, TokenResponse
from app.services import auth_service

router = APIRouter(
    prefix="/api/v1/auth", tags=["auth"], dependencies=[Depends(enforce_auth_origin)]
)
REFRESH_COOKIE = "refresh_token"
COOKIE_PATH = "/api/v1/auth"


def token_response(
    response: Response, pair: auth_service.TokenPair, settings: AppSettings
) -> TokenResponse:
    response.set_cookie(
        REFRESH_COOKIE,
        pair.refresh_token,
        httponly=True,
        samesite="strict",
        secure=settings.cookie_secure,
        path=COOKIE_PATH,
        max_age=settings.refresh_token_expire_days * 86400,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return pair.response


@router.post("/login", response_model=TokenResponse)
def login(
    credentials: Annotated[LoginRequest, Form()],
    request: Request,
    response: Response,
    session: DatabaseSession,
    settings: AppSettings,
) -> TokenResponse:
    request.app.state.login_limiter.check(
        request.client.host if request.client else "unknown", credentials.username
    )
    return token_response(response, auth_service.login(session, credentials, settings), settings)


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    response: Response,
    session: DatabaseSession,
    settings: AppSettings,
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> TokenResponse:
    return token_response(
        response, auth_service.refresh(session, refresh_token, settings), settings
    )


@router.post("/logout", response_model=MessageResponse)
def logout(
    response: Response,
    session: DatabaseSession,
    settings: AppSettings,
    employee: CurrentEmployee,
    token: BearerToken,
) -> MessageResponse:
    assert token is not None
    auth_service.logout(session, token, employee, settings)
    response.delete_cookie(
        REFRESH_COOKIE,
        path=COOKIE_PATH,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"
    return MessageResponse(message="Logged out.")


@router.post("/change-password", response_model=TokenResponse)
def change_password(
    payload: ChangePasswordRequest,
    response: Response,
    session: DatabaseSession,
    settings: AppSettings,
    employee: CurrentEmployee,
) -> TokenResponse:
    return token_response(
        response, auth_service.change_password(session, employee, payload, settings), settings
    )

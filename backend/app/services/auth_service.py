import hmac
import math
from dataclasses import dataclass, field
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import (
    create_token,
    decode_token,
    dummy_password_hash,
    hash_password,
    password_stamp,
    signing_key,
    token_digest,
    verify_password,
)
from app.models import Employee, RefreshSession, Role
from app.schemas.auth import ChangePasswordRequest, LoginRequest, TokenResponse
from app.utils.time import utc_now


@dataclass
class TokenPair:
    response: TokenResponse
    refresh_token: str = field(repr=False)


def load_employee(
    session: Session,
    employee_id: int,
    *,
    lock: bool = False,
    include_permissions: bool = True,
) -> Employee | None:
    query = (
        select(Employee)
        .where(Employee.id == employee_id)
        .options(joinedload(Employee.role), joinedload(Employee.team))
        .execution_options(populate_existing=True)
    )
    if include_permissions:
        query = query.options(joinedload(Employee.role).selectinload(Role.permissions))
    if lock:
        query = query.with_for_update()
    return session.execute(query).scalar_one_or_none()


def issue_tokens(
    session: Session,
    employee: Employee,
    settings: Settings,
    refresh_session: RefreshSession | None = None,
) -> TokenPair:
    now = utc_now()
    expires_at = now + timedelta(days=settings.refresh_token_expire_days)
    if refresh_session is None:
        refresh_session = RefreshSession(
            employee_id=employee.id, token_hash=token_digest(uuid4().hex), expires_at=expires_at
        )
        session.add(refresh_session)
        session.flush()
    access = create_token(employee, refresh_session.id, "access", settings, now)
    refresh = create_token(employee, refresh_session.id, "refresh", settings, now)
    refresh_session.token_hash = token_digest(refresh)
    refresh_session.expires_at = expires_at
    session.flush()
    return TokenPair(
        TokenResponse(
            access_token=access,
            expires_in=settings.access_token_expire_minutes * 60,
            pwd_change_required=employee.must_change_password,
        ),
        refresh,
    )


def login(session: Session, credentials: LoginRequest, settings: Settings) -> TokenPair:
    signing_key(settings)
    employee = session.execute(
        select(Employee).where(Employee.employee_id == credentials.username).with_for_update()
    ).scalar_one_or_none()
    now = utc_now()
    if employee is None or not employee.is_active:
        verify_password(credentials.password.get_secret_value(), dummy_password_hash())
        raise AppError(401, "INVALID_CREDENTIALS", "Invalid employee ID or password.")
    if employee.locked_until and employee.locked_until > now:
        retry = max(1, math.ceil((employee.locked_until - now).total_seconds()))
        raise AppError(
            429,
            "ACCOUNT_LOCKED",
            "Account temporarily locked. Try again later.",
            headers={"Retry-After": str(retry)},
        )
    if employee.locked_until:
        employee.failed_login_count = 0
        employee.locked_until = None
    valid, updated_hash = verify_password(
        credentials.password.get_secret_value(), employee.password_hash
    )
    if not valid:
        employee.failed_login_count += 1
        if employee.failed_login_count >= settings.max_failed_logins:
            employee.locked_until = now + timedelta(minutes=settings.lockout_minutes)
        session.commit()  # Persist failures even though the HTTP request returns an error.
        if employee.locked_until:
            raise AppError(
                429,
                "ACCOUNT_LOCKED",
                "Account temporarily locked. Try again later.",
                headers={"Retry-After": str(settings.lockout_minutes * 60)},
            )
        raise AppError(401, "INVALID_CREDENTIALS", "Invalid employee ID or password.")
    if updated_hash:
        employee.password_hash = updated_hash
    employee.failed_login_count = 0
    employee.locked_until = None
    employee.last_login_at = now
    tokens = issue_tokens(session, employee, settings)
    session.commit()
    return tokens


def authenticate(session: Session, token: str, settings: Settings) -> Employee:
    claims = decode_token(token, "access", settings)
    employee = load_employee(session, int(claims.sub), include_permissions=False)
    if (
        employee is None
        or not employee.is_active
        or claims.pwd_changed_at != password_stamp(employee)
    ):
        raise AppError(
            401,
            "INVALID_TOKEN",
            "Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    active_session = session.get(RefreshSession, claims.sid, populate_existing=True)
    if (
        active_session is None
        or active_session.employee_id != employee.id
        or active_session.revoked_at is not None
        or active_session.expires_at <= utc_now()
    ):
        raise AppError(
            401,
            "INVALID_TOKEN",
            "Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return employee


def refresh(session: Session, token: str | None, settings: Settings) -> TokenPair:
    if token is None:
        raise AppError(401, "INVALID_TOKEN", "Invalid or expired token.")
    claims = decode_token(token, "refresh", settings)
    employee = load_employee(session, int(claims.sub), lock=True)
    active_session = session.execute(
        select(RefreshSession)
        .where(RefreshSession.id == claims.sid)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if (
        employee is None
        or not employee.is_active
        or claims.pwd_changed_at != password_stamp(employee)
        or active_session is None
        or active_session.employee_id != employee.id
        or active_session.revoked_at is not None
        or active_session.expires_at <= utc_now()
        or not hmac.compare_digest(active_session.token_hash, token_digest(token))
    ):
        raise AppError(401, "INVALID_TOKEN", "Invalid or expired token.")
    pair = issue_tokens(session, employee, settings, active_session)
    session.commit()
    return pair


def logout(session: Session, access_token: str, employee: Employee, settings: Settings) -> None:
    claims = decode_token(access_token, "access", settings)
    session.execute(
        update(RefreshSession)
        .where(
            RefreshSession.id == claims.sid,
            RefreshSession.employee_id == employee.id,
        )
        .values(revoked_at=utc_now())
    )
    session.commit()


def change_password(
    session: Session, employee: Employee, payload: ChangePasswordRequest, settings: Settings
) -> TokenPair:
    current = load_employee(session, employee.id, lock=True)
    if current is None or not current.is_active:
        raise AppError(401, "INVALID_TOKEN", "Invalid or expired token.")
    valid, _ = verify_password(payload.current_password.get_secret_value(), current.password_hash)
    if not valid:
        raise AppError(401, "INVALID_CREDENTIALS", "Current password is incorrect.")
    current.password_hash = hash_password(payload.new_password.get_secret_value())
    current.must_change_password = False
    current.password_changed_at = utc_now()
    current.failed_login_count = 0
    current.locked_until = None
    session.execute(
        update(RefreshSession)
        .where(RefreshSession.employee_id == current.id, RefreshSession.revoked_at.is_(None))
        .values(revoked_at=current.password_changed_at)
    )
    pair = issue_tokens(session, current, settings)
    session.commit()
    return pair

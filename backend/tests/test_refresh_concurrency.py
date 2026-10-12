from concurrent.futures import ThreadPoolExecutor
from secrets import token_urlsafe

from pydantic import SecretStr
from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import hash_password
from app.models import Employee, RefreshSession, Role
from app.schemas.auth import LoginRequest
from app.services.auth_service import login, refresh
from app.services.id_service import generate_employee_id
from app.services.reference_service import seed_reference_data


def test_concurrent_refresh_accepts_token_only_once(
    db_engine: Engine, auth_settings: Settings
) -> None:
    password = SecretStr(token_urlsafe(24) + "1")
    with Session(db_engine, expire_on_commit=False) as session:
        seed_reference_data(session)
        role_id = session.execute(select(Role.id).where(Role.name == "employee")).scalar_one()
        employee = Employee(
            employee_id=generate_employee_id(session, auth_settings),
            role_id=role_id,
            password_hash=hash_password(password.get_secret_value()),
            first_name="Refresh",
            last_name="Race",
        )
        session.add(employee)
        session.commit()
        employee_id = employee.id
        token = login(
            session, LoginRequest(username=employee.employee_id, password=password), auth_settings
        ).refresh_token

    def worker(_number: int) -> str:
        with Session(db_engine) as session:
            try:
                refresh(session, token, auth_settings)
            except AppError as error:
                return error.code
            return "success"

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(worker, range(2)))
        assert sorted(results) == ["INVALID_TOKEN", "success"]
    finally:
        with Session(db_engine) as session, session.begin():
            session.execute(delete(RefreshSession).where(RefreshSession.employee_id == employee_id))
            session.execute(delete(Employee).where(Employee.id == employee_id))

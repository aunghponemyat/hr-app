from collections.abc import Iterator
from secrets import token_urlsafe
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import Settings
from app.core.database import create_database_engine, get_db
from app.core.security import hash_password
from app.deps.auth import require_password_changed
from app.main import create_app
from app.models import Employee, Role
from app.schemas.auth import MessageResponse
from app.services.reference_service import seed_reference_data
from tests.database import migration_config, validate_test_database_url


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, app_env="test")


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings), raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    config = Settings()
    test_url = config.test_database_url.get_secret_value()
    validate_test_database_url(test_url, config.database_url.get_secret_value())
    engine = create_database_engine(test_url)
    try:
        with engine.begin() as connection:
            command.upgrade(migration_config(connection), "head")
    except SQLAlchemyError:
        engine.dispose()
        pytest.fail("Test MySQL is unavailable or migration failed; run make test-db-up.")
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    with db_engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            try:
                yield session
            finally:
                session.close()
                transaction.rollback()


@pytest.fixture
def seeded_session(db_session: Session) -> Session:
    seed_reference_data(db_session)
    return db_session


@pytest.fixture
def employee(seeded_session: Session) -> Employee:
    role_id = seeded_session.execute(select(Role.id).where(Role.name == "employee")).scalar_one()
    result = Employee(
        employee_id="TEST0001",
        password_hash="$argon2id$test-fixture-placeholder",
        role_id=role_id,
        first_name="Test",
        last_name="Employee",
    )
    seeded_session.add(result)
    seeded_session.flush()
    return result


@pytest.fixture
def manager(seeded_session: Session) -> Employee:
    role_id = seeded_session.execute(
        select(Role.id).where(Role.name == "reporting_manager")
    ).scalar_one()
    result = Employee(
        employee_id="TESTMGR",
        password_hash="$argon2id$test-fixture-placeholder",
        role_id=role_id,
        first_name="Test",
        last_name="Manager",
    )
    seeded_session.add(result)
    seeded_session.flush()
    return result


@pytest.fixture
def auth_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        jwt_secret_key=token_urlsafe(48),
        login_rate_limit_ip=200,
        login_rate_limit_employee=100,
    )


@pytest.fixture
def initial_password() -> SecretStr:
    return SecretStr("InitialPass123")


@pytest.fixture
def auth_employee(
    employee: Employee, seeded_session: Session, initial_password: SecretStr
) -> Employee:
    employee.password_hash = hash_password(initial_password.get_secret_value())
    seeded_session.flush()
    return employee


@pytest.fixture
def auth_app(seeded_session: Session, auth_settings: Settings) -> FastAPI:
    app = create_app(auth_settings)

    def override_db() -> Iterator[Session]:
        yield seeded_session

    app.dependency_overrides[get_db] = override_db

    @app.get("/api/v1/test-protected", response_model=MessageResponse)
    def protected(
        employee: Annotated[Employee, Depends(require_password_changed)],
    ) -> MessageResponse:
        return MessageResponse(message=f"Welcome {employee.employee_id}")

    return app


@pytest.fixture
def auth_client(auth_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(auth_app, raise_server_exceptions=False) as client:
        yield client

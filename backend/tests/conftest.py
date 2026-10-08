from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import Settings
from app.core.database import create_database_engine
from app.main import create_app
from app.models import Employee, Role
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

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import verify_password
from app.models import Employee, Role
from app.schemas.bootstrap import AdminCreateRequest
from app.services.bootstrap_service import create_admin
from app.services.id_service import generate_employee_id
from app.services.reference_service import seed_reference_data
from scripts import create_admin as bootstrap_cli
from scripts.create_admin import read_initial_password
from tests.test_auth import CHANGE, LOGIN, bearer


def admin_request(
    password: SecretStr, *, force: bool = False, employee_id: str | None = None
) -> AdminCreateRequest:
    return AdminCreateRequest(
        first_name="Admin",
        last_name="User",
        password=password,
        role="hr",
        force=force,
        employee_id=employee_id,
    )


def test_bootstrap_login_password_change_normal_access(
    auth_client: TestClient,
    seeded_session: Session,
    auth_settings: Settings,
    initial_password: SecretStr,
) -> None:
    admin = create_admin(seeded_session, admin_request(initial_password), auth_settings)
    login_response = auth_client.post(
        LOGIN,
        data={
            "username": admin.employee_id,
            "password": initial_password.get_secret_value(),
        },
    )
    assert login_response.status_code == 200
    initial_token = str(login_response.json()["access_token"])
    profile = auth_client.get("/api/v1/me", headers=bearer(initial_token))
    assert profile.status_code == 200 and profile.json()["role"]["name"] == "hr"
    assert "employee.create.any" in profile.json()["permissions"]
    assert (
        auth_client.get("/api/v1/test-protected", headers=bearer(initial_token)).status_code == 403
    )
    changed = auth_client.post(
        CHANGE,
        headers=bearer(initial_token),
        json={
            "current_password": initial_password.get_secret_value(),
            "new_password": "NewAdmin123",
        },
    )
    assert changed.status_code == 200
    assert (
        auth_client.get(
            "/api/v1/test-protected", headers=bearer(str(changed.json()["access_token"]))
        ).status_code
        == 200
    )


def test_bootstrap_creates_hashed_admin_with_forced_change(
    db_session: Session, auth_settings: Settings, initial_password: SecretStr
) -> None:
    employee = create_admin(db_session, admin_request(initial_password), auth_settings)
    assert employee.employee_id.startswith("EMP") and len(employee.employee_id) >= 7
    assert employee.must_change_password and employee.is_active
    assert employee.role.name == "hr"
    assert employee.password_hash.startswith("$argon2id$")
    assert verify_password(initial_password.get_secret_value(), employee.password_hash)[0]
    assert employee.password_hash != initial_password.get_secret_value()


def test_second_bootstrap_refused_even_if_admin_inactive(
    db_session: Session, auth_settings: Settings, initial_password: SecretStr
) -> None:
    employee = create_admin(db_session, admin_request(initial_password), auth_settings)
    employee.is_active = False
    db_session.flush()
    with pytest.raises(AppError) as error, db_session.begin_nested():
        create_admin(db_session, admin_request(initial_password), auth_settings)
    assert error.value.code == "ADMIN_EXISTS"
    assert db_session.execute(select(func.count()).select_from(Employee)).scalar_one() == 1


def test_force_bootstrap_creates_another_admin(
    db_session: Session, auth_settings: Settings, initial_password: SecretStr
) -> None:
    first = create_admin(db_session, admin_request(initial_password), auth_settings)
    second = create_admin(db_session, admin_request(initial_password, force=True), auth_settings)
    assert first.employee_id != second.employee_id


def test_override_advances_employee_sequence(
    db_session: Session, auth_settings: Settings, initial_password: SecretStr
) -> None:
    employee = create_admin(
        db_session, admin_request(initial_password, employee_id="EMP0099"), auth_settings
    )
    assert employee.employee_id == "EMP0099"
    assert generate_employee_id(db_session, auth_settings) == "EMP0100"


def test_duplicate_override_rejected(
    db_session: Session, auth_settings: Settings, initial_password: SecretStr
) -> None:
    create_admin(db_session, admin_request(initial_password, employee_id="CUSTOM"), auth_settings)
    with pytest.raises(AppError) as error, db_session.begin_nested():
        create_admin(
            db_session,
            admin_request(initial_password, force=True, employee_id="CUSTOM"),
            auth_settings,
        )
    assert error.value.code == "EMPLOYEE_ID_EXISTS"


def test_bootstrap_c_level(
    db_session: Session, auth_settings: Settings, initial_password: SecretStr
) -> None:
    payload = AdminCreateRequest(
        first_name="Admin", last_name="User", role="c_level", password=initial_password
    )
    assert create_admin(db_session, payload, auth_settings).role.name == "c_level"


@pytest.mark.parametrize("password", ["short1", "12345678", "abcdefgh"])
def test_bootstrap_password_policy(password: str) -> None:
    with pytest.raises(ValidationError):
        admin_request(SecretStr(password))


def test_password_input_precedence_and_confirmation() -> None:
    def must_not_prompt(_message: str) -> str:
        raise AssertionError("Prompt should not be called.")

    assert (
        read_initial_password("argument", "environment", must_not_prompt).get_secret_value()
        == "argument"
    )
    assert (
        read_initial_password(None, "environment", must_not_prompt).get_secret_value()
        == "environment"
    )
    values = iter(["InitialPass123", "InitialPass123"])
    assert (
        read_initial_password(None, None, lambda _: next(values)).get_secret_value()
        == "InitialPass123"
    )
    values = iter(["InitialPass123", "Different123"])
    with pytest.raises(ValueError):
        read_initial_password(None, None, lambda _: next(values))


@pytest.fixture
def cli_database(
    monkeypatch: pytest.MonkeyPatch, db_session: Session, auth_settings: Settings
) -> Callable[[], Session]:
    connection = db_session.connection()

    def factory() -> Session:
        return Session(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        )

    monkeypatch.setattr(bootstrap_cli, "SessionLocal", factory)
    monkeypatch.setattr(bootstrap_cli, "get_settings", lambda: auth_settings)
    return factory


def test_cli_environment_password_and_existing_admin_does_not_prompt(
    cli_database: Callable[[], Session],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    initial_password: SecretStr,
) -> None:
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", initial_password.get_secret_value())
    arguments = ["--first-name", "Admin", "--last-name", "User", "--role", "hr"]
    assert bootstrap_cli.main(arguments) == 0
    output = capsys.readouterr()
    assert output.out.startswith("Admin created: EMP")
    assert initial_password.get_secret_value() not in output.out + output.err
    monkeypatch.delenv("ADMIN_INITIAL_PASSWORD")

    def fail_prompt(_message: str) -> str:
        raise AssertionError("An existing admin should abort before prompting.")

    monkeypatch.setattr(bootstrap_cli, "getpass", fail_prompt)
    assert bootstrap_cli.main(arguments) == 1
    assert "already exists" in capsys.readouterr().err


def test_cli_invalid_password_is_redacted(
    cli_database: Callable[[], Session],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", "private")
    assert bootstrap_cli.main(["--first-name", "Admin", "--last-name", "User"]) == 1
    output = capsys.readouterr()
    assert "private" not in output.out + output.err


def test_concurrent_employee_ids_are_unique(db_engine: Engine, auth_settings: Settings) -> None:
    with Session(db_engine) as session, session.begin():
        seed_reference_data(session)
        role_id = session.execute(select(Role.id).where(Role.name == "employee")).scalar_one()

    def worker(_number: int) -> str:
        with Session(db_engine) as session, session.begin():
            identifier = generate_employee_id(session, auth_settings)
            session.add(
                Employee(
                    employee_id=identifier,
                    role_id=role_id,
                    password_hash="$argon2id$fixture",
                    first_name="Concurrent",
                    last_name="Employee",
                )
            )
            session.flush()
            return identifier

    identifiers: list[str] = []
    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            identifiers = list(executor.map(worker, range(8)))
        assert len(identifiers) == len(set(identifiers)) == 8
    finally:
        with Session(db_engine) as session, session.begin():
            session.execute(delete(Employee).where(Employee.employee_id.in_(identifiers)))

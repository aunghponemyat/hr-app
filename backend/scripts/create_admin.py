import argparse
import os
import sys
from collections.abc import Callable, Sequence
from getpass import getpass

from pydantic import SecretStr, ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.errors import AppError
from app.schemas.bootstrap import AdminCreateRequest
from app.services.bootstrap_service import create_admin, prepare_bootstrap


def read_initial_password(
    supplied: str | None,
    environment: str | None,
    prompt: Callable[[str], str] = getpass,
) -> SecretStr:
    if supplied is not None:
        return SecretStr(supplied)
    if environment is not None:
        return SecretStr(environment)
    password = prompt("Initial admin password: ")
    if password != prompt("Confirm initial admin password: "):
        raise ValueError("Passwords do not match.")
    return SecretStr(password)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create the first HR application admin.")
    parser.add_argument("--first-name", required=True)
    parser.add_argument("--last-name", required=True)
    parser.add_argument("--role", choices=("hr", "c_level"), default="hr")
    parser.add_argument("--employee-id")
    parser.add_argument(
        "--password", help="Initial password; prefer the prompt or environment variable."
    )
    parser.add_argument("--force", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        with SessionLocal() as session, session.begin():
            prepare_bootstrap(session, arguments.force)
            password = read_initial_password(
                arguments.password, os.environ.get("ADMIN_INITIAL_PASSWORD"), getpass
            )
            payload = AdminCreateRequest(
                first_name=arguments.first_name,
                last_name=arguments.last_name,
                role=arguments.role,
                employee_id=arguments.employee_id,
                password=password,
                force=arguments.force,
            )
            employee = create_admin(session, payload, get_settings())
            business_id = employee.employee_id
    except ValidationError:
        print(
            "Invalid admin fields. Names/ID are required and the password must be "
            "8–1024 characters with letters and digits.",
            file=sys.stderr,
        )
        return 1
    except (ValueError, EOFError, KeyboardInterrupt):
        print("Admin creation cancelled or password confirmation failed.", file=sys.stderr)
        return 1
    except AppError as exc:
        print(exc.message, file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print("Admin creation failed. Check database connectivity and migrations.", file=sys.stderr)
        return 1
    print(f"Admin created: {business_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

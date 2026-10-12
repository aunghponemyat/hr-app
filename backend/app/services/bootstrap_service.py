from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import hash_password
from app.models import Employee, Role
from app.schemas.bootstrap import AdminCreateRequest
from app.services.id_service import (
    generate_employee_id,
    lock_employee_id_sequence,
    reserve_employee_id,
)
from app.services.reference_service import seed_reference_data


def prepare_bootstrap(session: Session, force: bool) -> None:
    """Bootstrap-only role-name checks; the caller owns the transaction."""
    seed_reference_data(session)
    lock_employee_id_sequence(session)  # Serializes bootstrap checks and generated/custom IDs.
    existing_admin = session.execute(
        select(Employee.id)
        .join(Role)
        .where(Role.name.in_(("hr", "c_level")))
        .with_for_update()
        .limit(1)
    ).scalar_one_or_none()
    if existing_admin is not None and not force:
        raise AppError(
            409, "ADMIN_EXISTS", "An admin already exists. Use --force to create another."
        )


def create_admin(session: Session, payload: AdminCreateRequest, settings: Settings) -> Employee:
    prepare_bootstrap(session, payload.force)
    role_id = session.execute(select(Role.id).where(Role.name == payload.role)).scalar_one()
    business_id = (
        reserve_employee_id(session, payload.employee_id, settings)
        if payload.employee_id
        else generate_employee_id(session, settings)
    )
    employee = Employee(
        employee_id=business_id,
        password_hash=hash_password(payload.password.get_secret_value()),
        first_name=payload.first_name,
        last_name=payload.last_name,
        role_id=role_id,
        must_change_password=True,
        is_active=True,
    )
    session.add(employee)
    session.flush()
    return employee

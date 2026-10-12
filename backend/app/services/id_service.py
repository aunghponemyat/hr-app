from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.models import Employee, IdSequence


def lock_employee_id_sequence(session: Session) -> IdSequence:
    sequence = session.execute(
        select(IdSequence)
        .where(IdSequence.name == "employee_id")
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if sequence is None:
        raise AppError(
            409, "REFERENCE_DATA_REQUIRED", "Seed reference data before creating employees."
        )
    return sequence


def generate_employee_id(session: Session, settings: Settings) -> str:
    sequence = lock_employee_id_sequence(session)
    while sequence.next_value < 2**64 - 1:
        candidate = (
            f"{settings.employee_id_prefix}{sequence.next_value:0{settings.employee_id_pad}d}"
        )
        if len(candidate) > 20:
            break
        sequence.next_value += 1
        exists = session.execute(
            select(Employee.id).where(Employee.employee_id == candidate).with_for_update()
        ).scalar_one_or_none()
        if exists is None:
            session.flush()
            return candidate
    raise AppError(409, "EMPLOYEE_ID_EXHAUSTED", "Employee ID capacity has been exhausted.")


def reserve_employee_id(session: Session, employee_id: str, settings: Settings) -> str:
    sequence = lock_employee_id_sequence(session)
    exists = session.execute(
        select(Employee.id).where(Employee.employee_id == employee_id).with_for_update()
    ).scalar_one_or_none()
    if exists is not None:
        raise AppError(409, "EMPLOYEE_ID_EXISTS", "Employee ID already exists.")
    suffix = employee_id.removeprefix(settings.employee_id_prefix)
    if suffix != employee_id and suffix.isascii() and suffix.isdigit():
        value = int(suffix)
        if value >= 2**64 - 1:
            raise AppError(409, "EMPLOYEE_ID_EXHAUSTED", "Employee ID capacity has been exhausted.")
        sequence.next_value = max(sequence.next_value, value + 1)
        session.flush()
    return employee_id

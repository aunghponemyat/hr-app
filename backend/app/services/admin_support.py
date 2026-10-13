from collections.abc import Iterator
from contextlib import contextmanager
from typing import TypeVar
from zoneinfo import ZoneInfo

from pydantic import JsonValue
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.models import AuditLog, Employee
from app.models.base import Base
from app.schemas.admin import EmployeeResponse, PageQuery
from app.schemas.auth import RoleSummary, TeamSummary
from app.services.authorization_service import AuthorizationContext, has_permission
from app.services.id_service import lock_employee_id_sequence

Entity = TypeVar("Entity", bound=Base)


def require_any(caller: AuthorizationContext, resource: str, action: str) -> None:
    if "any" not in has_permission(caller, resource, action):
        raise AppError(403, "PERMISSION_DENIED", "Permission denied.")


@contextmanager
def mutation(caller: AuthorizationContext, resource: str, action: str) -> Iterator[None]:
    require_any(caller, resource, action)
    session = caller.session
    try:
        # All administrative writers take this lock first, including ID allocation.
        lock_employee_id_sequence(session)
        yield
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise AppError(
            409, "CONFLICT", "A duplicate or referenced record prevents this change."
        ) from exc
    except Exception:
        session.rollback()
        raise


def get_entity(
    session: Session, model: type[Entity], entity_id: int, *, lock: bool = False
) -> Entity:
    entity = session.get(model, entity_id, populate_existing=True, with_for_update=lock)
    if entity is None:
        raise AppError(404, "NOT_FOUND", "Record not found.")
    return entity


def page_rows(
    session: Session, query: Select[tuple[Entity]], page: PageQuery
) -> tuple[list[Entity], int]:
    total = session.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    rows = list(
        session.scalars(query.offset((page.page - 1) * page.page_size).limit(page.page_size))
    )
    return rows, total


def employee_response(employee: Employee, settings: Settings) -> EmployeeResponse:
    zone = ZoneInfo(settings.app_timezone)
    return EmployeeResponse(
        id=employee.id,
        employee_id=employee.employee_id,
        first_name=employee.first_name,
        last_name=employee.last_name,
        display_name=employee.display_name,
        position=employee.position,
        department=employee.department,
        is_active=employee.is_active,
        must_change_password=employee.must_change_password,
        role=RoleSummary(id=employee.role.id, name=employee.role.name),
        team=TeamSummary(id=employee.team.id, name=employee.team.name) if employee.team else None,
        created_at=employee.created_at.astimezone(zone),
        updated_at=employee.updated_at.astimezone(zone),
    )


def audit(
    caller: AuthorizationContext,
    action: str,
    entity: str,
    entity_id: int,
    before: dict[str, JsonValue] | None = None,
    after: dict[str, JsonValue] | None = None,
) -> None:
    caller.session.add(
        AuditLog(
            actor_id=caller.employee.id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            before_json=before,
            after_json=after,
        )
    )

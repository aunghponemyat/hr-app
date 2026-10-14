from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import JsonValue
from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import joinedload

from app.core.config import Settings
from app.core.errors import AppError
from app.models import Employee, LeaveReason, LeaveRequest, LeaveType
from app.models.enums import LeaveStatus
from app.schemas.admin import PageResponse
from app.schemas.leave import LeaveCreate, LeaveDecision, LeaveQuery, LeaveResponse, TeamLeaveQuery
from app.services.admin_support import audit, get_entity, page_rows
from app.services.authorization_service import (
    AuthorizationContext,
    authorize,
    has_permission,
    resolve_target_employee,
    scoped_employee_ids_query,
)
from app.services.leave_options_service import eligible_managers
from app.services.leave_presenter import leave_response
from app.services.leave_validation_service import check_overlap, compute_end_date
from app.utils.time import utc_now


@contextmanager
def leave_transaction(caller: AuthorizationContext) -> Iterator[None]:
    try:
        yield
        caller.session.commit()
    except IntegrityError as exc:
        caller.session.rollback()
        raise AppError(409, "LEAVE_CONFLICT", "Leave changed; reload and retry.") from exc
    except OperationalError as exc:
        caller.session.rollback()
        if exc.orig is not None and exc.orig.args and exc.orig.args[0] in {1205, 1213}:
            raise AppError(409, "LEAVE_CONFLICT", "Leave changed; reload and retry.") from exc
        raise
    except Exception:
        caller.session.rollback()
        raise


def lock_people(caller: AuthorizationContext, employee_ids: set[int]) -> dict[int, Employee]:
    people = {
        employee.id: employee
        for employee in caller.session.scalars(
            select(Employee)
            .where(Employee.id.in_(employee_ids))
            .order_by(Employee.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    }
    if caller.employee.id in people:
        employee = people[caller.employee.id]
        if not employee.is_active:
            raise AppError(401, "INVALID_TOKEN", "Invalid authentication token.")
        if employee.must_change_password:
            raise AppError(
                403, "PASSWORD_CHANGE_REQUIRED", "Change your password before continuing."
            )
    return people


def state_snapshot(row: LeaveRequest) -> dict[str, JsonValue]:
    return {
        "status": row.status.value,
        "decided_by": row.decided_by,
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        "decision_note": row.decision_note,
    }


def create(caller: AuthorizationContext, data: LeaveCreate, settings: Settings) -> LeaveResponse:
    authorize(caller, "leave", "create", caller.employee)
    if data.reporting_manager_id == caller.employee.id:
        raise AppError(422, "INELIGIBLE_MANAGER", "Choose a reporting manager other than yourself.")
    with leave_transaction(caller):
        people = lock_people(caller, {caller.employee.id, data.reporting_manager_id})
        employee = people[caller.employee.id]
        today = utc_now().astimezone(ZoneInfo(settings.app_timezone)).date()
        end_date = compute_end_date(data, today, settings)
        leave_type = get_entity(caller.session, LeaveType, data.leave_type_id)
        reason = get_entity(caller.session, LeaveReason, data.leave_reason_id)
        if not leave_type.is_active or not reason.is_active:
            raise AppError(422, "INACTIVE_LEAVE_OPTION", "Choose active leave options.")
        if reason.requires_text and not (data.reason_text and data.reason_text.strip()):
            raise AppError(422, "REASON_TEXT_REQUIRED", "Describe the selected leave reason.")
        if data.reporting_manager_id not in {
            manager.id for manager in eligible_managers(caller.session, employee)
        }:
            raise AppError(
                422, "INELIGIBLE_MANAGER", "Choose a currently eligible reporting manager."
            )
        check_overlap(caller.session, employee.id, data, end_date)
        row = LeaveRequest(
            employee_id=employee.id,
            end_date=end_date,
            status=LeaveStatus.PENDING,
            **data.model_dump(),
        )
        caller.session.add(row)
        caller.session.flush()
        caller.session.refresh(row)
        response = leave_response(row, settings)
        audit(
            caller,
            "leave.create",
            "leave_request",
            row.id,
            after={
                "employee_id": row.employee_id,
                "reporting_manager_id": row.reporting_manager_id,
                "start_date": row.start_date.isoformat(),
                "end_date": row.end_date.isoformat(),
                "num_days": str(row.num_days),
                **state_snapshot(row),
            },
        )
        return response


def requests_query() -> Select[tuple[LeaveRequest]]:
    return (
        select(LeaveRequest)
        .options(
            joinedload(LeaveRequest.leave_type),
            joinedload(LeaveRequest.leave_reason),
            joinedload(LeaveRequest.employee).joinedload(Employee.team),
            joinedload(LeaveRequest.reporting_manager).joinedload(Employee.team),
            joinedload(LeaveRequest.decider).joinedload(Employee.team),
        )
        .execution_options(populate_existing=True)
    )


def list_requests(
    caller: AuthorizationContext, query: LeaveQuery, settings: Settings, *, team: bool = False
) -> PageResponse[LeaveResponse]:
    scopes = has_permission(caller, "leave", "read")
    allowed = {"team", "any"} if team else {"self", "any"}
    if not scopes.intersection(allowed):
        raise AppError(403, "PERMISSION_DENIED", "Permission denied.")
    statement = requests_query().where(
        LeaveRequest.employee_id.in_(scoped_employee_ids_query(caller, "leave", "read"))
    )
    if not team:
        statement = statement.where(LeaveRequest.employee_id == caller.employee.id)
    elif isinstance(query, TeamLeaveQuery) and query.employee_id is not None:
        resolve_target_employee(caller, "leave", "read", query.employee_id)
        statement = statement.where(LeaveRequest.employee_id == query.employee_id)
    if query.status is not None:
        statement = statement.where(LeaveRequest.status == query.status)
    rows, total = page_rows(
        caller.session,
        statement.order_by(LeaveRequest.created_at.desc(), LeaveRequest.id.desc()),
        query,
    )
    return PageResponse(
        items=[leave_response(row, settings) for row in rows],
        total=total,
        page=query.page,
        page_size=query.page_size,
    )


def get_request(caller: AuthorizationContext, request_id: int, settings: Settings) -> LeaveResponse:
    scopes = has_permission(caller, "leave", "read")
    if not scopes:
        raise AppError(403, "PERMISSION_DENIED", "Permission denied.")
    statement = requests_query().where(LeaveRequest.id == request_id)
    expanded = bool(scopes.intersection({"team", "any"}))
    if not expanded:
        statement = statement.where(LeaveRequest.employee_id == caller.employee.id)
    row = caller.session.scalar(statement)
    if row is None:
        if expanded:
            raise AppError(404, "NOT_FOUND", "Leave request not found.")
        raise AppError(403, "OUT_OF_SCOPE", "Leave request is outside your permitted scope.")
    authorize(caller, "leave", "read", row.employee)
    return leave_response(row, settings)


def decide(
    caller: AuthorizationContext,
    request_id: int,
    data: LeaveDecision,
    settings: Settings,
    decision: Literal["approve", "reject"],
) -> LeaveResponse:
    scopes = has_permission(caller, "leave", "decide")
    if not scopes.intersection({"team", "any"}):
        raise AppError(403, "PERMISSION_DENIED", "Permission denied.")
    with leave_transaction(caller):
        initial = get_entity(caller.session, LeaveRequest, request_id)
        people = lock_people(caller, {caller.employee.id, initial.employee_id})
        row = get_entity(caller.session, LeaveRequest, request_id, lock=True)
        if row.employee_id == caller.employee.id:
            raise AppError(
                403, "SELF_APPROVAL_FORBIDDEN", "You cannot decide your own leave request."
            )
        authorize(caller, "leave", "decide", people[row.employee_id])
        if "any" not in scopes and row.reporting_manager_id != caller.employee.id:
            raise AppError(
                403,
                "NOT_SELECTED_MANAGER",
                "Only the selected reporting manager can decide this request.",
            )
        if row.status != LeaveStatus.PENDING:
            raise AppError(409, "INVALID_STATE", "Only pending requests can be decided.")
        before = state_snapshot(row)
        row.status = LeaveStatus.APPROVED if decision == "approve" else LeaveStatus.REJECTED
        row.decided_by = caller.employee.id
        row.decided_at = utc_now()
        row.decision_note = data.decision_note
        caller.session.flush()
        caller.session.refresh(row)
        audit(caller, f"leave.{decision}", "leave_request", row.id, before, state_snapshot(row))
        return leave_response(row, settings)


def cancel(caller: AuthorizationContext, request_id: int, settings: Settings) -> LeaveResponse:
    with leave_transaction(caller):
        lock_people(caller, {caller.employee.id})
        row = caller.session.scalar(
            select(LeaveRequest)
            .where(LeaveRequest.id == request_id, LeaveRequest.employee_id == caller.employee.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise AppError(403, "OUT_OF_SCOPE", "Only the requester can cancel this leave request.")
        today = utc_now().astimezone(ZoneInfo(settings.app_timezone)).date()
        if row.status != LeaveStatus.PENDING and not (
            row.status == LeaveStatus.APPROVED and row.start_date > today
        ):
            raise AppError(409, "INVALID_STATE", "This request can no longer be cancelled.")
        before = state_snapshot(row)
        row.status = LeaveStatus.CANCELLED
        caller.session.flush()
        caller.session.refresh(row)
        audit(caller, "leave.cancel", "leave_request", row.id, before, state_snapshot(row))
        return leave_response(row, settings)

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier
from uuid import uuid4

from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.models import AuditLog, Employee, LeaveRequest, Role
from app.models.enums import LeaveStatus
from app.schemas.leave import LeaveCreate, LeaveDecision
from app.services.authorization_service import AuthorizationContext, load_permissions
from app.services.leave_service import cancel, create, decide
from app.services.reference_service import seed_reference_data
from tests.attendance_support import AttendanceClock
from tests.leave_support import leave_payload


def test_concurrent_overlap_submissions_and_decisions_are_serialized(
    db_engine: Engine,
    auth_settings: Settings,
    attendance_clock: AttendanceClock,
) -> None:
    with Session(db_engine) as session, session.begin():
        seed_reference_data(session)
        employee_role = session.scalar(select(Role.id).where(Role.name == "employee"))
        admin_role = session.scalar(select(Role.id).where(Role.name == "hr"))
        assert employee_role is not None and admin_role is not None
        requester = Employee(
            employee_id=f"LEAVE{uuid4().hex[:12]}",
            role_id=employee_role,
            first_name="Concurrent",
            last_name="Requester",
            password_hash="$argon2id$test-fixture",
            must_change_password=False,
        )
        manager = Employee(
            employee_id=f"MGR{uuid4().hex[:12]}",
            role_id=admin_role,
            first_name="Concurrent",
            last_name="Manager",
            password_hash="$argon2id$test-fixture",
            must_change_password=False,
        )
        session.add_all([requester, manager])
        session.flush()
        requester_id, manager_id = requester.id, manager.id
        payload = LeaveCreate.model_validate(leave_payload(session, manager))
    barrier = Barrier(4)

    def submit(_index: int) -> str:
        with Session(db_engine) as session:
            employee = session.get(Employee, requester_id)
            assert employee is not None
            caller = AuthorizationContext(
                employee, session, load_permissions(session, employee.role_id)
            )
            barrier.wait(timeout=10)
            try:
                create(caller, payload, auth_settings)
                return "created"
            except AppError as error:
                return error.code

    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            assert sorted(executor.map(submit, range(4))) == ["LEAVE_OVERLAP"] * 3 + ["created"]
        with Session(db_engine) as session:
            row = session.scalars(
                select(LeaveRequest).where(LeaveRequest.employee_id == requester_id)
            ).one()
            request_id = row.id
        decision_barrier = Barrier(2)

        def make_decision(action: str) -> str:
            with Session(db_engine) as session:
                actor = session.get(Employee, manager_id)
                assert actor is not None
                caller = AuthorizationContext(
                    actor, session, load_permissions(session, actor.role_id)
                )
                decision_barrier.wait(timeout=10)
                try:
                    if action == "approve":
                        decide(caller, request_id, LeaveDecision(), auth_settings, "approve")
                    else:
                        decide(caller, request_id, LeaveDecision(), auth_settings, "reject")
                    return "decided"
                except AppError as error:
                    return error.code

        with ThreadPoolExecutor(max_workers=2) as executor:
            assert sorted(executor.map(make_decision, ["approve", "reject"])) == [
                "INVALID_STATE",
                "decided",
            ]
        with Session(db_engine) as session:
            decided_row = session.get(LeaveRequest, request_id)
            assert decided_row is not None and decided_row.status in {
                LeaveStatus.APPROVED,
                LeaveStatus.REJECTED,
            }
            logs = session.scalars(
                select(AuditLog).where(
                    AuditLog.entity == "leave_request", AuditLog.entity_id == request_id
                )
            ).all()
            assert len(logs) == 2  # One creation and one decision.
        with Session(db_engine) as session:
            current_requester = session.get(Employee, requester_id)
            assert current_requester is not None
            caller = AuthorizationContext(
                current_requester, session, load_permissions(session, current_requester.role_id)
            )
            current_request = create(
                caller,
                LeaveCreate.model_validate(
                    {
                        **payload.model_dump(),
                        "start_date": date(2026, 10, 14),
                        "num_days": 1,
                    }
                ),
                auth_settings,
            )
            current_id = current_request.id
        cancel_barrier = Barrier(2)

        def cancel_or_approve(action: str) -> str:
            with Session(db_engine) as session:
                actor = session.get(Employee, requester_id if action == "cancel" else manager_id)
                assert actor is not None
                caller = AuthorizationContext(
                    actor, session, load_permissions(session, actor.role_id)
                )
                cancel_barrier.wait(timeout=10)
                try:
                    response = (
                        cancel(caller, current_id, auth_settings)
                        if action == "cancel"
                        else decide(caller, current_id, LeaveDecision(), auth_settings, "approve")
                    )
                    return response.status.value
                except AppError as error:
                    return error.code

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(cancel_or_approve, ["cancel", "approve"]))
        assert results.count("INVALID_STATE") == 1
        assert set(results).intersection({"approved", "cancelled"})
        with Session(db_engine) as session:
            final = session.get(LeaveRequest, current_id)
            assert final is not None and final.status.value in results
    finally:
        with Session(db_engine) as session, session.begin():
            ids = [requester_id, manager_id]
            session.execute(delete(AuditLog).where(AuditLog.actor_id.in_(ids)))
            session.execute(delete(LeaveRequest).where(LeaveRequest.employee_id == requester_id))
            session.execute(delete(Employee).where(Employee.id.in_(ids)))

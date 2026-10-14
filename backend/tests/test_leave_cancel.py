from datetime import date

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import AuditLog, Permission, RolePermission
from app.models.enums import LeaveStatus
from tests.attendance_support import AttendanceClock
from tests.authz_support import AuthzScenario
from tests.leave_support import leave_record
from tests.test_auth import bearer, login_token


@pytest.mark.parametrize(
    "status,day,allowed",
    [
        (LeaveStatus.PENDING, date(2026, 10, 12), True),
        (LeaveStatus.PENDING, date(2026, 10, 14), True),
        (LeaveStatus.APPROVED, date(2026, 10, 15), True),
        (LeaveStatus.APPROVED, date(2026, 10, 14), False),
        (LeaveStatus.APPROVED, date(2026, 10, 13), False),
        (LeaveStatus.REJECTED, date(2026, 10, 15), False),
        (LeaveStatus.CANCELLED, date(2026, 10, 15), False),
    ],
)
def test_cancel_state_machine_and_audit(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
    status: LeaveStatus,
    day: date,
    allowed: bool,
) -> None:
    row = leave_record(
        seeded_session,
        scenario.employees["employee_a"],
        scenario.employees["manager_a"],
        day=day,
        status=status,
    )
    if status == LeaveStatus.APPROVED:
        row.decided_by = scenario.employees["manager_a"].id
        row.decided_at = attendance_clock.now()
        row.decision_note = "Approved earlier"
    seeded_session.add(row)
    headers = bearer(login_token(auth_client, scenario.employees["employee_a"], initial_password))
    response = auth_client.post(f"/api/v1/leave-requests/{row.id}/cancel", headers=headers)
    assert response.status_code == (200 if allowed else 409), response.text
    seeded_session.refresh(row)
    if allowed:
        assert row.status == LeaveStatus.CANCELLED
        log = seeded_session.scalars(select(AuditLog)).one()
        assert (
            log.action == "leave.cancel"
            and log.before_json is not None
            and log.before_json["status"] == status.value
        )
        if status == LeaveStatus.APPROVED:
            assert (
                row.decided_by == scenario.employees["manager_a"].id
                and row.decision_note == "Approved earlier"
            )
    else:
        assert row.status == status and response.json()["code"] == "INVALID_STATE"
        assert not seeded_session.scalars(select(AuditLog)).all()


@pytest.mark.parametrize("actor", ["employee_b", "manager_a", "hr", "c_level"])
def test_only_requester_can_cancel_including_admins(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
    actor: str,
) -> None:
    row = leave_record(
        seeded_session, scenario.employees["employee_a"], scenario.employees["manager_a"]
    )
    seeded_session.add(row)
    headers = bearer(login_token(auth_client, scenario.employees[actor], initial_password))
    response = auth_client.post(f"/api/v1/leave-requests/{row.id}/cancel", headers=headers)
    assert response.status_code == 403 and response.json()["code"] == "OUT_OF_SCOPE"


def test_requester_can_cancel_after_read_grant_revocation(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
) -> None:
    employee = scenario.employees["employee_a"]
    row = leave_record(seeded_session, employee, scenario.employees["manager_a"])
    seeded_session.add(row)
    headers = bearer(login_token(auth_client, employee, initial_password))
    permission = seeded_session.scalar(
        select(Permission.id).where(Permission.code == "leave.read.self")
    )
    seeded_session.execute(
        delete(RolePermission).where(
            RolePermission.role_id == employee.role_id, RolePermission.permission_id == permission
        )
    )
    seeded_session.commit()
    assert auth_client.get(f"/api/v1/leave-requests/{row.id}", headers=headers).status_code == 403
    assert (
        auth_client.post(f"/api/v1/leave-requests/{row.id}/cancel", headers=headers).status_code
        == 200
    )

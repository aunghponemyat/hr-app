from datetime import date

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LeaveReason, LeaveType
from tests.attendance_support import AttendanceClock, attendance_record
from tests.authz_support import AuthzScenario
from tests.leave_support import leave_record
from tests.test_auth import bearer, login_token
from tests.test_report_api import csv_rows
from tests.test_report_csv import ATTENDANCE_COLUMNS, LEAVE_COLUMNS


@pytest.mark.parametrize("trigger", ["=", "+", "-", "@", "\t", "\r"])
def test_all_user_controlled_csv_fields_escape_injection(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
    trigger: str,
) -> None:
    employee, manager, decider = (
        scenario.employees["employee_a"],
        scenario.employees["manager_a"],
        scenario.employees["hr"],
    )
    employee.employee_id = trigger + "EMP0001"
    employee.display_name = trigger + "Employee"
    manager.display_name = trigger + "Manager"
    decider.display_name = trigger + "Decider"
    scenario.teams["a"].name = trigger + "Team"
    leave_type = seeded_session.scalar(select(LeaveType).where(LeaveType.code == "annual"))
    reason = seeded_session.scalar(select(LeaveReason).where(LeaveReason.code == "vacation"))
    assert leave_type is not None and reason is not None
    leave_type.name = trigger + "Type"
    reason.name = trigger + "Reason"
    request = leave_record(seeded_session, employee, manager)
    request.reason_text = trigger + "Reason text"
    request.remark = trigger + "Remark"
    request.decided_by = decider.id
    seeded_session.add(request)
    seeded_session.add(attendance_record(employee, date(2026, 10, 13)))
    headers = bearer(login_token(auth_client, decider, initial_password))
    params = {"from": "2026-10-13", "to": "2026-10-14", "employee_id": employee.id}
    attendance = csv_rows(
        auth_client.get("/api/v1/admin/reports/attendance.csv", headers=headers, params=params),
        ATTENDANCE_COLUMNS,
    )
    for column, value in [("employee_id", "EMP0001"), ("name", "Employee"), ("team", "Team")]:
        assert attendance[0][column] == "'" + trigger + value
    leave = csv_rows(
        auth_client.get("/api/v1/admin/reports/leave.csv", headers=headers, params=params),
        LEAVE_COLUMNS,
    )
    assert len(leave) == 1
    for column, value in [
        ("employee_id", "EMP0001"),
        ("name", "Employee"),
        ("team", "Team"),
        ("leave_type", "Type"),
        ("reason", "Reason"),
        ("reason_text", "Reason text"),
        ("reporting_manager", "Manager"),
        ("decided_by", "Decider"),
        ("remark", "Remark"),
    ]:
        assert leave[0][column] == "'" + trigger + value

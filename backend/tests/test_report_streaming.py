import codecs
from collections.abc import Iterator
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import get_db
from app.main import create_app
from app.models import Employee
from app.schemas.attendance import DateRange
from app.schemas.report import AttendanceCsvRow, SelfExportQuery
from app.services import report_service
from app.services.authorization_service import AuthorizationContext, load_permissions
from tests.attendance_support import AttendanceClock
from tests.authz_support import AuthzScenario
from tests.leave_support import leave_record
from tests.test_auth import bearer, login_token
from tests.test_report_api import csv_rows
from tests.test_report_csv import ATTENDANCE_COLUMNS, LEAVE_COLUMNS


def test_database_dependency_stays_open_until_streaming_completes(
    auth_app: FastAPI,
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    def monitored_db() -> Iterator[Session]:
        events.append("db.open")
        try:
            yield seeded_session
        finally:
            events.append("db.close")

    auth_app.dependency_overrides[get_db] = monitored_db
    original = report_service.attendance_csv_rows

    def monitored_rows(
        caller: AuthorizationContext,
        employees: Select[tuple[Employee]],
        period: DateRange,
        settings: Settings,
        today: date,
    ) -> Iterator[AttendanceCsvRow]:
        assert "db.close" not in events
        events.append("stream.begin")
        try:
            yield from original(caller, employees, period, settings, today)
        finally:
            events.append("stream.end")

    headers = bearer(login_token(auth_client, scenario.employees["employee_a"], initial_password))
    events.clear()
    monkeypatch.setattr(report_service, "attendance_csv_rows", monitored_rows)
    response = auth_client.get(
        "/api/v1/attendance/export",
        headers=headers,
        params={"from": "2026-10-13", "to": "2026-10-14"},
    )
    assert len(csv_rows(response, ATTENDANCE_COLUMNS)) == 2
    assert events == ["db.open", "stream.begin", "stream.end", "db.close"]


def test_export_preparation_does_not_buffer_rows(
    scenario: AuthzScenario,
    seeded_session: Session,
    auth_settings: Settings,
    attendance_clock: AttendanceClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    employee = scenario.employees["employee_a"]
    caller = AuthorizationContext(
        employee, seeded_session, load_permissions(seeded_session, employee.role_id)
    )
    visited: list[str] = []
    original = report_service.attendance_csv_rows

    def rows(
        caller: AuthorizationContext,
        employees: Select[tuple[Employee]],
        period: DateRange,
        settings: Settings,
        today: date,
    ) -> Iterator[AttendanceCsvRow]:
        visited.append("started")
        yield from original(caller, employees, period, settings, today)

    monkeypatch.setattr(report_service, "attendance_csv_rows", rows)
    export = report_service.attendance_export(
        caller,
        SelfExportQuery.model_validate({"from": "2026-10-14", "to": "2026-10-14"}),
        auth_settings,
    )
    assert visited == []
    assert next(export.chunks) == codecs.BOM_UTF8 and visited == []
    assert next(export.chunks).startswith(b"employee_id,name,team,") and visited == []
    remaining = b"".join(export.chunks)
    assert visited == ["started"] and employee.employee_id.encode() in remaining


def test_batched_exports_do_not_truncate_or_repeat_rows(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(report_service, "EMPLOYEE_BATCH_SIZE", 2)
    monkeypatch.setattr(report_service, "LEAVE_BATCH_SIZE", 2)
    for employee in scenario.employees.values():
        manager = (
            scenario.employees["manager_a"]
            if employee.id != scenario.employees["manager_a"].id
            else scenario.employees["hr"]
        )
        seeded_session.add(leave_record(seeded_session, employee, manager))
    headers = bearer(login_token(auth_client, scenario.employees["hr"], initial_password))
    params = {"from": "2026-10-13", "to": "2026-10-14"}
    attendance = csv_rows(
        auth_client.get("/api/v1/admin/reports/attendance.csv", headers=headers, params=params),
        ATTENDANCE_COLUMNS,
    )
    identities = [(row["employee_id"], row["date"]) for row in attendance]
    assert len(identities) == len(set(identities)) == len(scenario.ids()) * 2
    ordered_ids = [
        employee.employee_id
        for employee in sorted(scenario.employees.values(), key=lambda employee: employee.id)
    ]
    assert identities == [
        (employee_id, day) for employee_id in ordered_ids for day in ["2026-10-13", "2026-10-14"]
    ]
    leave = csv_rows(
        auth_client.get("/api/v1/admin/reports/leave.csv", headers=headers, params=params),
        LEAVE_COLUMNS,
    )
    assert len(leave) == len(scenario.ids()) and [row["employee_id"] for row in leave] == [
        employee.employee_id for employee in scenario.employees.values()
    ]


def test_csv_endpoints_publish_root_string_response_schemas(auth_settings: Settings) -> None:
    document = create_app(auth_settings).openapi()
    for path in [
        "/api/v1/attendance/export",
        "/api/v1/admin/reports/attendance.csv",
        "/api/v1/admin/reports/leave.csv",
    ]:
        content = document["paths"][path]["get"]["responses"]["200"]["content"]
        assert set(content) == {"text/csv"}
        assert content["text/csv"]["schema"]["$ref"].endswith("/CsvDocument")
    assert document["components"]["schemas"]["CsvDocument"]["type"] == "string"

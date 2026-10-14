from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session

from tests.attendance_support import AttendanceClock, attendance_record
from tests.authz_support import AuthzScenario
from tests.test_auth import bearer, login_token


@pytest.mark.parametrize("actor", ["employee_a", "senior", "manager_a", "hr", "c_level"])
@pytest.mark.parametrize("target", ["employee_a", "employee_b", "unassigned"])
def test_production_read_target_scope_matrix(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    actor: str,
    target: str,
) -> None:
    caller, employee = scenario.employees[actor], scenario.employees[target]
    headers = bearer(login_token(auth_client, caller, initial_password))
    allowed = (
        actor in {"hr", "c_level"}
        or caller.id == employee.id
        or (actor == "manager_a" and employee.team_id == scenario.teams["a"].id)
    )
    for path in ["/attendance/calendar", "/attendance"]:
        response = auth_client.get(
            f"/api/v1{path}",
            headers=headers,
            params={"employee_id": employee.id, "from": "2026-10-12", "to": "2026-10-14"},
        )
        assert response.status_code == (200 if allowed else 403), response.text
        if not allowed:
            assert response.json()["code"] == "OUT_OF_SCOPE"


@pytest.mark.parametrize("actor", ["employee_a", "senior", "manager_a", "hr", "c_level"])
def test_table_effective_scope_counts_and_pagination(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    actor: str,
) -> None:
    caller = scenario.employees[actor]
    headers = bearer(login_token(auth_client, caller, initial_password))
    expected = (
        scenario.ids()
        if actor in {"hr", "c_level"}
        else scenario.team_ids("a")
        if actor == "manager_a"
        else {caller.id}
    )
    params: dict[str, Any] = {"from": "2026-10-12", "to": "2026-10-14", "page_size": 2}
    first = auth_client.get("/api/v1/attendance", headers=headers, params=params)
    assert first.status_code == 200 and first.json()["total"] == 3 * len(expected)
    seen: set[tuple[int, str]] = set()
    for page in range(1, (first.json()["total"] + 1) // 2 + 1):
        response = auth_client.get(
            "/api/v1/attendance", headers=headers, params={**params, "page": page}
        )
        assert response.status_code == 200
        for row in response.json()["items"]:
            pair = (row["employee"]["id"], row["date"])
            assert row["employee"]["id"] in expected and pair not in seen
            seen.add(pair)
    assert len(seen) == 3 * len(expected)
    assert (
        auth_client.get(
            "/api/v1/attendance", headers=headers, params={**params, "page": 100}
        ).json()["items"]
        == []
    )


def test_calendar_summary_missing_days_default_month_and_years(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
) -> None:
    employee = scenario.employees["employee_a"]
    for day, hours in [(date(2026, 10, 12), 8), (date(2026, 10, 13), 3)]:
        row = attendance_record(employee, day, hours=hours)
        if hours < 4:
            from app.models.enums import AttendanceStatus

            row.status = AttendanceStatus.HALF_DAY
        seeded_session.add(row)
    headers = bearer(login_token(auth_client, employee, initial_password))
    response = auth_client.get("/api/v1/attendance/calendar", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["period"] == {"from_date": "2026-10-01", "to_date": "2026-10-31"}
    assert len(data["entries"]) == 31 and data["available_years"] == [2026]
    entries = {row["date"]: row for row in data["entries"]}
    assert entries["2026-10-12"]["display_status"] == "present"
    assert entries["2026-10-13"]["display_status"] == "half-day"
    assert entries["2026-10-14"]["display_status"] is None
    assert entries["2026-10-10"]["display_status"] == "weekend"
    assert entries["2026-10-09"]["display_status"] == "absent"
    assert entries["2026-10-17"]["display_status"] == "upcoming"
    assert data["summary"] == {
        "present_days": 1,
        "half_day_days": 1,
        "leave_days": 0,
        "absent_days": 7,
        "total_worked_hours": 11.0,
    }
    assert entries["2026-10-12"]["clock_in"] == "2026-10-12T09:00:00+07:00"
    assert all(row["leave"] is None for row in data["entries"])


def test_stored_attendance_overrides_weekend_and_unfinished_interval_has_zero_hours(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
) -> None:
    employee = scenario.employees["employee_a"]
    row = attendance_record(employee, date(2026, 10, 10))
    row.clock_out = None
    seeded_session.add(row)
    headers = bearer(login_token(auth_client, employee, initial_password))
    response = auth_client.get(
        "/api/v1/attendance/calendar",
        headers=headers,
        params={"from": "2026-10-10", "to": "2026-10-10"},
    )
    assert response.json()["entries"][0]["display_status"] == "present"
    assert response.json()["summary"]["total_worked_hours"] == 0


@pytest.mark.parametrize("actor", ["employee_a", "manager_a", "hr", "c_level"])
def test_history_policy_on_calendar_table_and_team(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
    actor: str,
) -> None:
    caller = scenario.employees[actor]
    seeded_session.add(attendance_record(caller, date(2024, 5, 1)))
    headers = bearer(login_token(auth_client, caller, initial_password))
    paths = ["/attendance/calendar", "/attendance"] + (
        ["/team/attendance"] if actor != "employee_a" else []
    )
    for path in paths:
        response = auth_client.get(
            f"/api/v1{path}", headers=headers, params={"from": "2024-05-01", "to": "2024-05-02"}
        )
        assert response.status_code == (200 if actor in {"hr", "c_level"} else 422), response.text
        if actor not in {"hr", "c_level"}:
            assert response.json()["code"] == "HISTORY_LIMIT"
    period = auth_client.get(
        "/api/v1/attendance/calendar",
        headers=headers,
        params={"view": "year", "anchor": "2025-01-01"},
    ).json()["period"]
    assert period["from_date"] == ("2025-01-01" if actor in {"hr", "c_level"} else "2025-10-14")
    years = auth_client.get("/api/v1/attendance/calendar", headers=headers).json()[
        "available_years"
    ]
    assert years == ([2024] if actor in {"hr", "c_level"} else [2026])


@pytest.mark.parametrize(
    "params,code",
    [
        ({"from": "2025-01-01", "to": "2026-01-02"}, "RANGE_TOO_LARGE"),
        ({"from": "2026-10-14", "to": "2026-10-13"}, "INVALID_RANGE"),
        ({"from": "2026-10-01"}, "VALIDATION_ERROR"),
        ({"view": "custom"}, "VALIDATION_ERROR"),
        ({"view": "week", "from": "2026-10-01", "to": "2026-10-02"}, "VALIDATION_ERROR"),
        ({"page_size": 101}, "VALIDATION_ERROR"),
    ],
)
def test_range_and_query_validation_on_table(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    params: dict[str, Any],
    code: str,
) -> None:
    headers = bearer(login_token(auth_client, scenario.employees["hr"], initial_password))
    response = auth_client.get("/api/v1/attendance", headers=headers, params=params)
    assert response.status_code == 422 and response.json()["code"] == code, response.text


@pytest.mark.parametrize("actor", ["employee_a", "senior", "manager_a", "hr", "c_level"])
def test_team_summary_scopes_and_counts(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
    actor: str,
) -> None:
    seeded_session.add(attendance_record(scenario.employees["employee_a"], date(2026, 10, 12)))
    seeded_session.add(attendance_record(scenario.employees["employee_b"], date(2026, 10, 12)))
    headers = bearer(login_token(auth_client, scenario.employees[actor], initial_password))
    response = auth_client.get(
        "/api/v1/team/attendance",
        headers=headers,
        params={"from": "2026-10-12", "to": "2026-10-13"},
    )
    if actor in {"employee_a", "senior"}:
        assert response.status_code == 403
        return
    expected = scenario.ids() if actor in {"hr", "c_level"} else scenario.team_ids("a")
    assert response.status_code == 200 and response.json()["total"] == len(expected)
    items = {row["employee"]["id"]: row for row in response.json()["items"]}
    assert set(items) == expected
    assert items[scenario.employees["employee_a"].id]["summary"]["total_worked_hours"] == 8


def test_removed_manager_and_moved_member_stop_appearing_in_table_and_summary(
    auth_client: TestClient,
    scenario: AuthzScenario,
    initial_password: SecretStr,
    attendance_clock: AttendanceClock,
    seeded_session: Session,
) -> None:
    headers = bearer(login_token(auth_client, scenario.employees["manager_a"], initial_password))
    scenario.employees["employee_a"].team_id = scenario.teams["b"].id
    seeded_session.commit()
    params = {"from": "2026-10-14", "to": "2026-10-14"}
    for path in ["/attendance", "/team/attendance"]:
        data = auth_client.get(f"/api/v1{path}", headers=headers, params=params).json()
        assert scenario.employees["employee_a"].id not in {
            row["employee"]["id"] for row in data["items"]
        }
    scenario.managers["a"].removed_at = attendance_clock.now()
    seeded_session.commit()
    for path in ["/attendance", "/team/attendance"]:
        data = auth_client.get(f"/api/v1{path}", headers=headers, params=params).json()
        assert {row["employee"]["id"] for row in data["items"]} == {
            scenario.employees["manager_a"].id
        }

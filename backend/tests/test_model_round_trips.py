from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from app.models import (
    Attendance,
    AuditLog,
    Employee,
    LeaveReason,
    LeaveRequest,
    LeaveType,
    Team,
    TeamManager,
    TeamMember,
    WorkLocation,
)
from app.models.enums import AttendanceStatus, HalfDayPeriod, LeaveDuration, LeaveStatus, WorkMode


def test_employee_server_defaults_and_unicode(seeded_session: Session, employee: Employee) -> None:
    assert employee.is_active
    assert employee.must_change_password
    assert employee.failed_login_count == 0
    assert employee.password_changed_at is None
    assert employee.locked_until is None
    assert employee.last_login_at is None
    assert employee.created_at.tzinfo == timezone.utc
    assert employee.updated_at.tzinfo == timezone.utc
    assert abs((datetime.now(timezone.utc) - employee.created_at).total_seconds()) < 10
    previous_update = employee.updated_at
    employee.display_name = "พนักงาน 👩🏽‍💻"
    seeded_session.flush()
    seeded_session.refresh(employee)
    assert employee.display_name == "พนักงาน 👩🏽‍💻"
    assert employee.updated_at > previous_update


def test_utc_round_trip_preserves_instant_and_microseconds(
    seeded_session: Session, employee: Employee
) -> None:
    local_instant = datetime(2026, 10, 8, 9, 30, 0, 123456, tzinfo=ZoneInfo("Asia/Bangkok"))
    record = Attendance(
        employee_id=employee.id,
        attendance_date=date(2026, 10, 8),
        work_mode=WorkMode.REMOTE,
        status=AttendanceStatus.PRESENT,
        clock_in=local_instant,
    )
    seeded_session.add(record)
    seeded_session.flush()
    seeded_session.refresh(record)
    assert record.clock_in == local_instant.astimezone(timezone.utc)
    assert record.clock_in is not None and record.clock_in.tzinfo == timezone.utc
    assert record.clock_in.microsecond == 123456
    assert record.clock_in_verified is None and record.clock_out is None
    assert seeded_session.execute(text("SELECT @@session.time_zone")).scalar_one() == "+00:00"


def test_team_membership_manager_history_and_location_relationships(
    seeded_session: Session, employee: Employee, manager: Employee
) -> None:
    team = Team(name="Team A")
    location = WorkLocation(
        name="HQ Office", latitude=Decimal("13.756300"), longitude=Decimal("100.501800")
    )
    team.work_locations.append(location)
    employee.team = team
    seeded_session.flush()
    assert location.allowed_radius_m == 100
    first_join = datetime(2026, 10, 8, 2, 0, 0, 123456, tzinfo=timezone.utc)
    second_join = first_join + timedelta(microseconds=1)
    seeded_session.add_all(
        [
            TeamMember(
                team_id=team.id, employee_id=employee.id, joined_at=first_join, left_at=second_join
            ),
            TeamMember(team_id=team.id, employee_id=employee.id, joined_at=second_join),
            TeamManager(team_id=team.id, employee_id=manager.id, assigned_at=first_join),
        ]
    )
    seeded_session.flush()
    seeded_session.expire_all()
    assert employee.team is not None and employee.team.id == team.id
    assert employee in team.members
    assert len(team.membership_history) == 2
    assert len(team.manager_history) == 1
    assert team.manager_history[0].removed_at is None
    assert team.work_locations[0].id == location.id
    assert location.teams[0].id == team.id


def test_leave_request_and_audit_json_round_trip(
    seeded_session: Session, employee: Employee, manager: Employee
) -> None:
    leave_type = seeded_session.execute(
        select(LeaveType).where(LeaveType.code == "annual")
    ).scalar_one()
    reason = seeded_session.execute(
        select(LeaveReason).where(LeaveReason.code == "vacation")
    ).scalar_one()
    leave = LeaveRequest(
        employee_id=employee.id,
        leave_type_id=leave_type.id,
        leave_reason_id=reason.id,
        reporting_manager_id=manager.id,
        duration_type=LeaveDuration.HALF_DAY,
        half_day_period=HalfDayPeriod.MORNING,
        num_days=Decimal("0.5"),
        start_date=date(2026, 10, 8),
        end_date=date(2026, 10, 8),
    )
    seeded_session.add(leave)
    seeded_session.flush()
    audit = AuditLog(
        actor_id=manager.id,
        action="leave.approve",
        entity="leave_requests",
        entity_id=leave.id,
        before_json={"status": "pending"},
        after_json={"status": "approved", "note": "อนุมัติ"},
    )
    seeded_session.add(audit)
    seeded_session.flush()
    seeded_session.expire_all()
    assert leave.status == LeaveStatus.PENDING
    assert leave.employee.id == employee.id
    assert leave.reporting_manager.id == manager.id
    assert leave.leave_type.code == "annual"
    assert leave.leave_reason.code == "vacation"
    assert leave.decider is None
    assert audit.before_json == {"status": "pending"}
    assert audit.after_json == {"status": "approved", "note": "อนุมัติ"}
    assert audit.actor.id == manager.id


def test_fixture_rollback_survives_service_commit(db_session: Session, db_engine: Engine) -> None:
    db_session.add(Team(name="fixture-rollback-check"))
    db_session.commit()
    assert db_session.execute(
        select(Team.id).where(Team.name == "fixture-rollback-check")
    ).scalar_one()
    with db_engine.connect() as independent_connection:
        assert (
            independent_connection.execute(
                select(Team.id).where(Team.name == "fixture-rollback-check")
            ).scalar_one_or_none()
            is None
        )

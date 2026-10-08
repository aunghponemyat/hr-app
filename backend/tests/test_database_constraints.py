from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import delete, insert, select
from sqlalchemy.exc import IntegrityError, OperationalError, StatementError
from sqlalchemy.orm import Session

from app.models import (
    Attendance,
    Employee,
    IdSequence,
    LeaveReason,
    LeaveRequest,
    LeaveType,
    Permission,
    Role,
    RolePermission,
    WorkLocation,
)
from app.models.enums import AttendanceStatus, HalfDayPeriod, LeaveDuration, WorkMode


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("allowed_radius_m", Decimal("49")),
        ("allowed_radius_m", Decimal("101")),
        ("latitude", Decimal("-90.000001")),
        ("latitude", Decimal("90.000001")),
        ("longitude", Decimal("-180.000001")),
        ("longitude", Decimal("180.000001")),
    ],
)
def test_work_location_checks_reject_invalid_values(
    db_session: Session, field: str, value: Decimal
) -> None:
    values: dict[str, str | Decimal] = {
        "name": "Invalid location",
        "latitude": Decimal("13.7563"),
        "longitude": Decimal("100.5018"),
        "allowed_radius_m": Decimal("100"),
    }
    values[field] = value
    with pytest.raises(OperationalError) as error, db_session.begin_nested():
        db_session.execute(insert(WorkLocation).values(**values))
    assert error.value.orig is not None and error.value.orig.args[0] == 3819


@pytest.mark.parametrize(
    ("latitude", "longitude", "radius"),
    [("-90", "-180", 50), ("90", "180", 100)],
)
def test_location_check_boundaries_are_inclusive(
    db_session: Session, latitude: str, longitude: str, radius: int
) -> None:
    location = WorkLocation(
        name="Boundary",
        latitude=Decimal(latitude),
        longitude=Decimal(longitude),
        allowed_radius_m=radius,
    )
    db_session.add(location)
    db_session.flush()
    assert location.id > 0


def test_invalid_permission_scope_rejected(db_session: Session) -> None:
    with pytest.raises(OperationalError), db_session.begin_nested():
        db_session.execute(
            insert(Permission).values(
                code="profile.read.company", resource="profile", action="read", scope="company"
            )
        )


def test_sequence_cannot_be_zero(seeded_session: Session) -> None:
    with pytest.raises(OperationalError), seeded_session.begin_nested():
        seeded_session.execute(insert(IdSequence).values(name="invalid", next_value=0))


def test_attendance_is_unique_per_employee_and_date(
    seeded_session: Session, employee: Employee
) -> None:
    values = {
        "employee_id": employee.id,
        "attendance_date": date(2026, 10, 8),
        "work_mode": WorkMode.REMOTE,
        "status": AttendanceStatus.PRESENT,
    }
    seeded_session.execute(insert(Attendance).values(**values))
    with pytest.raises(IntegrityError) as error, seeded_session.begin_nested():
        seeded_session.execute(insert(Attendance).values(**values))
    assert error.value.orig is not None and error.value.orig.args[0] == 1062


def test_employee_business_id_is_unique(seeded_session: Session, employee: Employee) -> None:
    with pytest.raises(IntegrityError), seeded_session.begin_nested():
        seeded_session.execute(
            insert(Employee).values(
                employee_id=employee.employee_id,
                password_hash=employee.password_hash,
                role_id=employee.role_id,
                first_name="Another",
                last_name="Employee",
            )
        )


def test_attendance_foreign_key_rejects_nonexistent_employee(db_session: Session) -> None:
    with pytest.raises(IntegrityError) as error, db_session.begin_nested():
        db_session.execute(
            insert(Attendance).values(
                employee_id=2**63,
                attendance_date=date(2026, 10, 8),
                work_mode=WorkMode.REMOTE,
                status=AttendanceStatus.PRESENT,
            )
        )
    assert error.value.orig is not None and error.value.orig.args[0] == 1452


def test_clock_out_cannot_precede_clock_in(seeded_session: Session, employee: Employee) -> None:
    clock_in = datetime(2026, 10, 8, 2, tzinfo=timezone.utc)
    with pytest.raises(OperationalError), seeded_session.begin_nested():
        seeded_session.execute(
            insert(Attendance).values(
                employee_id=employee.id,
                attendance_date=date(2026, 10, 8),
                work_mode=WorkMode.REMOTE,
                status=AttendanceStatus.PRESENT,
                clock_in=clock_in,
                clock_out=clock_in - timedelta(seconds=1),
            )
        )


def test_naive_timestamps_rejected(seeded_session: Session, employee: Employee) -> None:
    with pytest.raises(StatementError), seeded_session.begin_nested():
        seeded_session.execute(
            insert(Attendance).values(
                employee_id=employee.id,
                attendance_date=date(2026, 10, 8),
                work_mode=WorkMode.REMOTE,
                status=AttendanceStatus.PRESENT,
                clock_in=datetime(2026, 10, 8, 2),
            )
        )


@pytest.mark.parametrize(
    ("duration", "num_days", "period"),
    [
        (LeaveDuration.HALF_DAY, "0.5", None),
        (LeaveDuration.HALF_DAY, "1", HalfDayPeriod.MORNING),
        (LeaveDuration.FULL_DAYS, "1.5", None),
        (LeaveDuration.FULL_DAYS, "0", None),
        (LeaveDuration.FULL_DAYS, "1", HalfDayPeriod.MORNING),
    ],
)
def test_leave_duration_check(
    seeded_session: Session,
    employee: Employee,
    manager: Employee,
    duration: LeaveDuration,
    num_days: str,
    period: HalfDayPeriod | None,
) -> None:
    leave_type = seeded_session.execute(
        select(LeaveType.id).where(LeaveType.code == "annual")
    ).scalar_one()
    reason = seeded_session.execute(
        select(LeaveReason.id).where(LeaveReason.code == "vacation")
    ).scalar_one()
    with pytest.raises(OperationalError), seeded_session.begin_nested():
        seeded_session.execute(
            insert(LeaveRequest).values(
                employee_id=employee.id,
                leave_type_id=leave_type,
                leave_reason_id=reason,
                reporting_manager_id=manager.id,
                duration_type=duration,
                num_days=Decimal(num_days),
                half_day_period=period,
                start_date=date(2026, 10, 8),
                end_date=date(2026, 10, 8),
            )
        )


def test_role_permission_foreign_keys_cascade_on_delete(db_session: Session) -> None:
    role = Role(name="temporary")
    permission = Permission(
        code="temporary.read.self", resource="temporary", action="read", scope="self"
    )
    role.permissions.append(permission)
    db_session.add(role)
    db_session.flush()
    role_id, permission_id = role.id, permission.id
    # Bypass ORM association cleanup so this proves the database cascade itself.
    db_session.execute(delete(Role).where(Role.id == role_id))
    assert db_session.get(RolePermission, (role_id, permission_id)) is None

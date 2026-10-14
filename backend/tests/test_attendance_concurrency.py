from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.models import Attendance, Employee, Role
from app.models.enums import WorkMode
from app.schemas.attendance import ClockRequest
from app.services.attendance_service import clock
from app.services.authorization_service import AuthorizationContext, load_permissions
from app.services.reference_service import seed_reference_data
from tests.attendance_support import AttendanceClock


def test_simultaneous_clock_actions_only_write_once(
    db_engine: Engine,
    auth_settings: Settings,
    attendance_clock: AttendanceClock,
) -> None:
    with Session(db_engine) as session, session.begin():
        seed_reference_data(session)
        role_id = session.scalar(select(Role.id).where(Role.name == "employee"))
        assert role_id is not None
        employee = Employee(
            employee_id=f"CLOCK{uuid4().hex[:12]}",
            role_id=role_id,
            first_name="Concurrent",
            last_name="Employee",
            password_hash="$argon2id$test-fixture",
            must_change_password=False,
        )
        session.add(employee)
        session.flush()
        employee_id = employee.id

    def race(clock_out: bool) -> list[str]:
        barrier = Barrier(4)

        def worker(_index: int) -> str:
            with Session(db_engine) as session:
                employee = session.get(Employee, employee_id)
                assert employee is not None
                caller = AuthorizationContext(
                    employee, session, load_permissions(session, employee.role_id)
                )
                barrier.wait(timeout=10)
                try:
                    clock(
                        caller,
                        ClockRequest(work_mode=WorkMode.REMOTE),
                        auth_settings,
                        clock_out=clock_out,
                    )
                    return "ok"
                except AppError as error:
                    return error.code

        with ThreadPoolExecutor(max_workers=4) as executor:
            return list(executor.map(worker, range(4)))

    try:
        assert sorted(race(False)) == ["ALREADY_CLOCKED_IN"] * 3 + ["ok"]
        attendance_clock.advance(hours=8)
        assert sorted(race(True)) == ["ALREADY_CLOCKED_OUT"] * 3 + ["ok"]
        with Session(db_engine) as session:
            row = session.scalars(
                select(Attendance).where(Attendance.employee_id == employee_id)
            ).one()
            assert row.clock_in is not None and row.clock_out is not None
            assert (row.clock_out - row.clock_in).total_seconds() == 8 * 3600
    finally:
        with Session(db_engine) as session, session.begin():
            session.execute(delete(Attendance).where(Attendance.employee_id == employee_id))
            session.execute(delete(Employee).where(Employee.id == employee_id))

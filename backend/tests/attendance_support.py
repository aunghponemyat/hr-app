from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.models import Attendance, Employee
from app.models.enums import AttendanceStatus, WorkMode


@dataclass
class AttendanceClock:
    value: datetime = datetime(2026, 10, 14, 2, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self.value

    def advance(self, **kwargs: float) -> None:
        self.value += timedelta(**kwargs)


def attendance_record(
    employee: Employee,
    day: date,
    *,
    hours: float = 8,
    mode: WorkMode = WorkMode.REMOTE,
    status: AttendanceStatus = AttendanceStatus.PRESENT,
) -> Attendance:
    clock_in = datetime.combine(day, datetime.min.time()).replace(
        hour=9, tzinfo=ZoneInfo("Asia/Bangkok")
    )
    return Attendance(
        employee_id=employee.id,
        attendance_date=day,
        work_mode=mode,
        clock_in=clock_in,
        clock_out=clock_in + timedelta(hours=hours),
        status=status,
    )

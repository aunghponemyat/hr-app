from enum import Enum


class WorkMode(str, Enum):
    ONSITE = "onsite"
    REMOTE = "remote"


class AttendanceStatus(str, Enum):
    PRESENT = "present"
    ABSENT = "absent"
    HALF_DAY = "half-day"


class LeaveDuration(str, Enum):
    HALF_DAY = "half_day"
    FULL_DAYS = "full_days"


class HalfDayPeriod(str, Enum):
    MORNING = "morning"
    AFTERNOON = "afternoon"


class LeaveStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


def enum_values(enum_class: type[Enum]) -> list[str]:
    return [str(member.value) for member in enum_class]

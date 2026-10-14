from calendar import monthrange
from datetime import date, timedelta

from app.core.config import Settings
from app.core.errors import AppError
from app.schemas.attendance import DateRange, PeriodQuery


def history_start(today: date) -> date:
    try:
        return today.replace(year=today.year - 1)
    except ValueError:
        return today.replace(year=today.year - 1, day=28)


def resolve_period(
    query: PeriodQuery, today: date, settings: Settings, *, unrestricted: bool
) -> DateRange:
    anchor = query.anchor or today
    view = query.view or ("custom" if query.from_date is not None else "month")
    try:
        if view == "custom":
            assert query.from_date is not None and query.to_date is not None
            start, end = query.from_date, query.to_date
        elif view == "week":
            start = anchor - timedelta(days=anchor.weekday())
            end = start + timedelta(days=6)
        elif view == "year":
            start, end = date(anchor.year, 1, 1), date(anchor.year, 12, 31)
        else:
            start = anchor.replace(day=1)
            end = anchor.replace(day=monthrange(anchor.year, anchor.month)[1])
        if end < start:
            raise AppError(422, "INVALID_RANGE", "The end date must be on or after the start date.")
        if (end - start).days + 1 > settings.max_report_range_days:
            raise AppError(
                422, "RANGE_TOO_LARGE", f"Select at most {settings.max_report_range_days} days."
            )
        if not unrestricted:
            earliest = history_start(today)
            if end < earliest:
                raise AppError(
                    422, "HISTORY_LIMIT", "Attendance history is limited to the past year."
                )
            start = max(start, earliest)
    except (OverflowError, ValueError) as exc:
        raise AppError(422, "INVALID_RANGE", "The requested period cannot be represented.") from exc
    return DateRange(from_date=start, to_date=end)

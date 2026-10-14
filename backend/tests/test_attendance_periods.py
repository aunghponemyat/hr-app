from datetime import date

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import AppError
from app.schemas.attendance import PeriodQuery
from app.services.period_service import history_start, resolve_period

TODAY = date(2026, 10, 14)


@pytest.mark.parametrize(
    "view,anchor,start,end",
    [
        (None, None, date(2026, 10, 1), date(2026, 10, 31)),
        ("week", date(2026, 10, 18), date(2026, 10, 12), date(2026, 10, 18)),
        ("month", date(2024, 2, 15), date(2024, 2, 1), date(2024, 2, 29)),
        ("year", date(2024, 2, 15), date(2024, 1, 1), date(2024, 12, 31)),
    ],
)
def test_calendar_periods(
    settings: Settings, view: str | None, anchor: date | None, start: date, end: date
) -> None:
    query = PeriodQuery.model_validate({"view": view, "anchor": anchor})
    period = resolve_period(query, TODAY, settings, unrestricted=True)
    assert period.from_date == start and period.to_date == end


def test_inclusive_cap_history_clip_and_leap_anniversary(settings: Settings) -> None:
    query = PeriodQuery.model_validate({"from": "2025-10-13", "to": "2026-10-13"})
    assert resolve_period(query, TODAY, settings, unrestricted=True).from_date == date(2025, 10, 13)
    assert resolve_period(query, TODAY, settings, unrestricted=False).from_date == date(
        2025, 10, 14
    )
    assert history_start(date(2024, 2, 29)) == date(2023, 2, 28)
    query = PeriodQuery.model_validate({"from": "2025-10-12", "to": "2026-10-13"})
    with pytest.raises(AppError) as error:
        resolve_period(query, TODAY, settings, unrestricted=False)
    assert error.value.code == "RANGE_TOO_LARGE"


@pytest.mark.parametrize(
    "bounds,code",
    [
        ({"from": "2026-10-14", "to": "2026-10-13"}, "INVALID_RANGE"),
        ({"from": "2020-01-01", "to": "2020-01-02"}, "HISTORY_LIMIT"),
    ],
)
def test_invalid_or_unavailable_periods(
    settings: Settings, bounds: dict[str, str], code: str
) -> None:
    with pytest.raises(AppError) as error:
        resolve_period(PeriodQuery.model_validate(bounds), TODAY, settings, unrestricted=False)
    assert error.value.code == code


@pytest.mark.parametrize(
    "values",
    [
        {"from": "2026-10-01"},
        {"to": "2026-10-01"},
        {"view": "custom"},
        {"view": "month", "from": "2026-10-01", "to": "2026-10-02"},
        {"anchor": "2026-10-01", "from": "2026-10-01", "to": "2026-10-02"},
    ],
)
def test_period_schema_rejects_ambiguous_inputs(values: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        PeriodQuery.model_validate(values)

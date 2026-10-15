import codecs
import csv
from collections.abc import Iterator
from datetime import date, datetime, timezone
from decimal import Decimal
from io import StringIO

import pytest
from pydantic import BaseModel

from app.schemas.report import AttendanceCsvRow, LeaveCsvRow
from app.services.csv_service import csv_cell, csv_chunks, export_filename

ATTENDANCE_COLUMNS = [
    "employee_id",
    "name",
    "team",
    "date",
    "display_status",
    "work_mode",
    "work_location",
    "clock_in_local",
    "clock_out_local",
    "worked_hours",
    "clock_in_verified",
    "clock_out_verified",
    "clock_in_distance_m",
    "clock_out_distance_m",
]
LEAVE_COLUMNS = [
    "employee_id",
    "name",
    "team",
    "leave_type",
    "reason",
    "reason_text",
    "duration",
    "num_days",
    "start_date",
    "end_date",
    "reporting_manager",
    "status",
    "decided_by",
    "decided_at",
    "remark",
]


@pytest.mark.parametrize(
    "value", ["=SUM(1,1)", "+cmd", "-formula", "@SUM(A1)", "\tvalue", "\rvalue"]
)
def test_injection_trigger_is_escaped(value: str) -> None:
    assert csv_cell(value) == "'" + value


@pytest.mark.parametrize(
    "value",
    [
        "Normal name",
        "ไทย မြန်မာ",
        "hello, world",
        'hello "world"',
        "line1\nline2",
        "",
        " space",
        "inside=equals",
    ],
)
def test_safe_text_is_preserved(value: str) -> None:
    assert csv_cell(value) == value


def test_typed_cells_and_exact_header_order() -> None:
    assert csv_cell(None) == "" and csv_cell(True) == "true" and csv_cell(False) == "false"
    assert csv_cell(Decimal("12.30")) == "12.30" and csv_cell(0) == "0"
    assert csv_cell(date(2026, 10, 14)) == "2026-10-14"
    assert csv_cell(datetime(2026, 10, 14, 2, tzinfo=timezone.utc)) == "2026-10-14T02:00:00+00:00"
    assert list(AttendanceCsvRow.model_fields) == ATTENDANCE_COLUMNS
    assert list(LeaveCsvRow.model_fields) == LEAVE_COLUMNS


def test_stream_is_lazy_bom_once_and_excel_csv_round_trip() -> None:
    class Row(BaseModel):
        value: str

    visited: list[int] = []
    values = ['ไทย, "မြန်မာ"\nnext line', "=SUM(1,1)"]

    def rows() -> Iterator[Row]:
        for index, value in enumerate(values):
            visited.append(index)
            yield Row(value=value)

    chunks = csv_chunks(Row, rows())
    assert next(chunks) == codecs.BOM_UTF8 and visited == []
    assert next(chunks) == b"value\r\n" and visited == []
    body = codecs.BOM_UTF8 + b"value\r\n" + b"".join(chunks)
    assert visited == [0, 1] and body.count(codecs.BOM_UTF8) == 1
    parsed = list(csv.DictReader(StringIO(body.decode("utf-8-sig"), newline="")))
    assert parsed == [{"value": values[0]}, {"value": "'" + values[1]}]


def test_empty_csv_still_has_bom_and_header_and_safe_filename() -> None:
    body = b"".join(csv_chunks(LeaveCsvRow, []))
    assert body == codecs.BOM_UTF8 + (",".join(LEAVE_COLUMNS) + "\r\n").encode()
    filename = export_filename("attendance", 'EMP"/\r\nไทย', date(2026, 1, 1), date(2026, 3, 31))
    assert filename == "attendance_EMP________2026-01-01_2026-03-31.csv"
    assert (
        '"' not in filename
        and "/" not in filename
        and "\r" not in filename
        and "\n" not in filename
    )

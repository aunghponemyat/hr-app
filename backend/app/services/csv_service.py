import codecs
import csv
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from io import StringIO

from pydantic import BaseModel


@dataclass(frozen=True)
class CsvExport:
    filename: str
    chunks: Iterator[bytes] = field(repr=False)


def csv_cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Enum):
        value = value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    text = str(value)
    if isinstance(value, str) and text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text


def csv_chunks(model: type[BaseModel], rows: Iterable[BaseModel]) -> Iterator[bytes]:
    yield codecs.BOM_UTF8
    buffer = StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    columns = list(model.model_fields)
    writer.writerow(columns)
    yield buffer.getvalue().encode("utf-8")
    for row in rows:
        buffer.seek(0)
        buffer.truncate(0)
        values = row.model_dump(mode="python")
        writer.writerow([csv_cell(values[column]) for column in columns])
        yield buffer.getvalue().encode("utf-8")


def export_filename(kind: str, owner: str, start: date, end: date) -> str:
    safe_owner = re.sub(r"[^A-Za-z0-9_-]", "_", owner)
    return f"{kind}_{safe_owner}_{start.isoformat()}_{end.isoformat()}.csv"

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from starlette.responses import StreamingResponse

from app.deps.auth import AppSettings
from app.deps.authz import AuthorizationContext, require_permission
from app.schemas.report import AdminExportQuery, CsvDocument, SelfExportQuery
from app.services import report_service as service
from app.services.csv_service import CsvExport

router = APIRouter(prefix="/api/v1", tags=["reports"])
# FastAPI uses the additional-response schema for non-JSON response classes.
CSV_RESPONSES: dict[int | str, dict[str, object]] = {
    200: {"model": CsvDocument, "description": "UTF-8 CSV with a leading BOM and ordered header."}
}
SelfExporter = Annotated[
    AuthorizationContext,
    Depends(require_permission("report", "export", allowed_scopes=frozenset({"self", "any"}))),
]
AdminExporter = Annotated[
    AuthorizationContext,
    Depends(require_permission("report", "export", allowed_scopes=frozenset({"any"}))),
]


class CsvStreamingResponse(StreamingResponse):
    media_type = "text/csv"


def csv_response(export: CsvExport) -> CsvStreamingResponse:
    return CsvStreamingResponse(
        export.chunks, headers={"Content-Disposition": f"attachment; filename={export.filename}"}
    )


@router.get(
    "/attendance/export",
    response_class=CsvStreamingResponse,
    response_model=CsvDocument,
    responses=CSV_RESPONSES,
)
def own_attendance(
    caller: SelfExporter, query: Annotated[SelfExportQuery, Query()], settings: AppSettings
) -> CsvStreamingResponse:
    return csv_response(service.attendance_export(caller, query, settings))


@router.get(
    "/admin/reports/attendance.csv",
    response_class=CsvStreamingResponse,
    response_model=CsvDocument,
    responses=CSV_RESPONSES,
)
def attendance(
    caller: AdminExporter, query: Annotated[AdminExportQuery, Query()], settings: AppSettings
) -> CsvStreamingResponse:
    return csv_response(service.attendance_export(caller, query, settings))


@router.get(
    "/admin/reports/leave.csv",
    response_class=CsvStreamingResponse,
    response_model=CsvDocument,
    responses=CSV_RESPONSES,
)
def leave(
    caller: AdminExporter, query: Annotated[AdminExportQuery, Query()], settings: AppSettings
) -> CsvStreamingResponse:
    return csv_response(service.leave_export(caller, query, settings))

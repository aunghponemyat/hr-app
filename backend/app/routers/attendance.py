from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.deps.auth import AppSettings
from app.deps.authz import AuthorizationContext, require_permission
from app.schemas.admin import PositiveId
from app.schemas.attendance import (
    AttendanceQuery,
    AttendanceResponse,
    AttendanceTableResponse,
    AttendanceUpdate,
    CalendarQuery,
    CalendarResponse,
    ClockRequest,
    ClockResponse,
    TodayResponse,
)
from app.services import attendance_read_service as reads
from app.services import attendance_service as service

router = APIRouter(prefix="/api/v1/attendance", tags=["attendance"])
Reader = Annotated[AuthorizationContext, Depends(require_permission("attendance", "read"))]
OwnReader = Annotated[
    AuthorizationContext,
    Depends(require_permission("attendance", "read", allowed_scopes=frozenset({"self", "any"}))),
]
Creator = Annotated[
    AuthorizationContext,
    Depends(require_permission("attendance", "create", allowed_scopes=frozenset({"self", "any"}))),
]
Editor = Annotated[
    AuthorizationContext,
    Depends(require_permission("attendance", "update", allowed_scopes=frozenset({"team", "any"}))),
]


@router.get("/today", response_model=TodayResponse)
def today(caller: OwnReader, settings: AppSettings) -> TodayResponse:
    return service.today(caller, settings)


@router.post("/clock-in", response_model=ClockResponse)
def clock_in(caller: Creator, data: ClockRequest, settings: AppSettings) -> ClockResponse:
    return service.clock(caller, data, settings, clock_out=False)


@router.post("/clock-out", response_model=ClockResponse)
def clock_out(caller: Creator, data: ClockRequest, settings: AppSettings) -> ClockResponse:
    return service.clock(caller, data, settings, clock_out=True)


@router.get("/calendar", response_model=CalendarResponse)
def calendar(
    caller: Reader, query: Annotated[CalendarQuery, Query()], settings: AppSettings
) -> CalendarResponse:
    return reads.calendar(caller, query, settings)


@router.get("", response_model=AttendanceTableResponse)
def table(
    caller: Reader, query: Annotated[AttendanceQuery, Query()], settings: AppSettings
) -> AttendanceTableResponse:
    return reads.table(caller, query, settings)


@router.patch("/{attendance_id}", response_model=AttendanceResponse)
def update(
    caller: Editor, attendance_id: PositiveId, data: AttendanceUpdate, settings: AppSettings
) -> AttendanceResponse:
    return service.update_attendance(caller, attendance_id, data, settings)

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.deps.auth import AppSettings
from app.deps.authz import AuthorizationContext, PasswordChangedCaller, require_permission
from app.schemas.admin import PageResponse, PositiveId
from app.schemas.leave import (
    LeaveCreate,
    LeaveDecision,
    LeaveOptions,
    LeaveQuery,
    LeaveResponse,
    TeamLeaveQuery,
)
from app.services import leave_service as service
from app.services.leave_options_service import options

router = APIRouter(prefix="/api/v1", tags=["leave"])
Creator = Annotated[
    AuthorizationContext,
    Depends(require_permission("leave", "create", allowed_scopes=frozenset({"self", "any"}))),
]
Reader = Annotated[AuthorizationContext, Depends(require_permission("leave", "read"))]
OwnReader = Annotated[
    AuthorizationContext,
    Depends(require_permission("leave", "read", allowed_scopes=frozenset({"self", "any"}))),
]
TeamReader = Annotated[
    AuthorizationContext,
    Depends(require_permission("leave", "read", allowed_scopes=frozenset({"team", "any"}))),
]
Decider = Annotated[
    AuthorizationContext,
    Depends(require_permission("leave", "decide", allowed_scopes=frozenset({"team", "any"}))),
]


@router.get("/leave/options", response_model=LeaveOptions)
def leave_options(caller: Creator, settings: AppSettings) -> LeaveOptions:
    return options(caller, settings)


@router.post("/leave-requests", response_model=LeaveResponse, status_code=201)
def create(caller: Creator, data: LeaveCreate, settings: AppSettings) -> LeaveResponse:
    return service.create(caller, data, settings)


@router.get("/leave-requests", response_model=PageResponse[LeaveResponse])
def personal(
    caller: OwnReader, query: Annotated[LeaveQuery, Query()], settings: AppSettings
) -> PageResponse[LeaveResponse]:
    return service.list_requests(caller, query, settings)


@router.get("/leave-requests/team", response_model=PageResponse[LeaveResponse])
def team(
    caller: TeamReader, query: Annotated[TeamLeaveQuery, Query()], settings: AppSettings
) -> PageResponse[LeaveResponse]:
    return service.list_requests(caller, query, settings, team=True)


@router.get("/leave-requests/{request_id}", response_model=LeaveResponse)
def detail(caller: Reader, request_id: PositiveId, settings: AppSettings) -> LeaveResponse:
    return service.get_request(caller, request_id, settings)


@router.post("/leave-requests/{request_id}/approve", response_model=LeaveResponse)
def approve(
    caller: Decider,
    request_id: PositiveId,
    settings: AppSettings,
    data: LeaveDecision | None = None,
) -> LeaveResponse:
    return service.decide(caller, request_id, data or LeaveDecision(), settings, "approve")


@router.post("/leave-requests/{request_id}/reject", response_model=LeaveResponse)
def reject(
    caller: Decider,
    request_id: PositiveId,
    settings: AppSettings,
    data: LeaveDecision | None = None,
) -> LeaveResponse:
    return service.decide(caller, request_id, data or LeaveDecision(), settings, "reject")


@router.post("/leave-requests/{request_id}/cancel", response_model=LeaveResponse)
def cancel(
    caller: PasswordChangedCaller, request_id: PositiveId, settings: AppSettings
) -> LeaveResponse:
    return service.cancel(caller, request_id, settings)

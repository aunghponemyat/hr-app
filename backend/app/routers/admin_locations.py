from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.deps.authz import AuthorizationContext, require_permission
from app.schemas.admin import (
    LocationCreate,
    LocationResponse,
    LocationUpdate,
    PageQuery,
    PageResponse,
    PositiveId,
)
from app.schemas.auth import MessageResponse
from app.services import location_service as service

router = APIRouter(prefix="/api/v1/admin/work-locations", tags=["location administration"])
Manager = Annotated[
    AuthorizationContext,
    Depends(require_permission("location", "manage", allowed_scopes=frozenset({"any"}))),
]


@router.get("", response_model=PageResponse[LocationResponse])
def locations(
    caller: Manager, query: Annotated[PageQuery, Query()]
) -> PageResponse[LocationResponse]:
    return service.list_locations(caller, query)


@router.post("", response_model=LocationResponse, status_code=201)
def create(caller: Manager, data: LocationCreate) -> LocationResponse:
    return service.create_location(caller, data)


@router.get("/{location_id}", response_model=LocationResponse)
def detail(caller: Manager, location_id: PositiveId) -> LocationResponse:
    return service.get_location(caller, location_id)


@router.patch("/{location_id}", response_model=LocationResponse)
def update(caller: Manager, location_id: PositiveId, data: LocationUpdate) -> LocationResponse:
    return service.update_location(caller, location_id, data)


@router.delete("/{location_id}", response_model=MessageResponse)
def delete(caller: Manager, location_id: PositiveId) -> MessageResponse:
    return service.delete_location(caller, location_id)

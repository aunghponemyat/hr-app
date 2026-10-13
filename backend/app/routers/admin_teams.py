from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.deps.auth import AppSettings
from app.deps.authz import AuthorizationContext, require_permission
from app.schemas.admin import (
    EmployeeAssignment,
    EmployeeResponse,
    LocationAssignment,
    LocationResponse,
    ManagerResponse,
    PageQuery,
    PageResponse,
    PositiveId,
    TeamCreate,
    TeamResponse,
    TeamUpdate,
)
from app.schemas.auth import MessageResponse
from app.services import team_service as service

router = APIRouter(prefix="/api/v1/admin/teams", tags=["team administration"])
Manager = Annotated[
    AuthorizationContext,
    Depends(require_permission("team", "manage", allowed_scopes=frozenset({"any"}))),
]


@router.get("", response_model=PageResponse[TeamResponse])
def teams(caller: Manager, query: Annotated[PageQuery, Query()]) -> PageResponse[TeamResponse]:
    return service.list_teams(caller, query)


@router.post("", response_model=TeamResponse, status_code=201)
def create(caller: Manager, data: TeamCreate) -> TeamResponse:
    return service.create_team(caller, data)


@router.get("/{team_id}", response_model=TeamResponse)
def detail(caller: Manager, team_id: PositiveId) -> TeamResponse:
    return service.get_team(caller, team_id)


@router.patch("/{team_id}", response_model=TeamResponse)
def update(caller: Manager, team_id: PositiveId, data: TeamUpdate) -> TeamResponse:
    return service.update_team(caller, team_id, data)


@router.delete("/{team_id}", response_model=MessageResponse)
def delete(caller: Manager, team_id: PositiveId) -> MessageResponse:
    return service.delete_team(caller, team_id)


@router.get("/{team_id}/members", response_model=PageResponse[EmployeeResponse])
def members(
    caller: Manager,
    team_id: PositiveId,
    query: Annotated[PageQuery, Query()],
    settings: AppSettings,
) -> PageResponse[EmployeeResponse]:
    return service.list_members(caller, team_id, query, settings)


@router.post("/{team_id}/members", response_model=EmployeeResponse)
def add_member(
    caller: Manager, team_id: PositiveId, data: EmployeeAssignment, settings: AppSettings
) -> EmployeeResponse:
    return service.assign_member(caller, team_id, data.employee_id, settings)


@router.delete("/{team_id}/members/{employee_id}", response_model=MessageResponse)
def remove_member(caller: Manager, team_id: PositiveId, employee_id: PositiveId) -> MessageResponse:
    return service.remove_member(caller, team_id, employee_id)


@router.get("/{team_id}/managers", response_model=PageResponse[ManagerResponse])
def managers(
    caller: Manager,
    team_id: PositiveId,
    query: Annotated[PageQuery, Query()],
    settings: AppSettings,
) -> PageResponse[ManagerResponse]:
    return service.list_managers(caller, team_id, query, settings)


@router.post("/{team_id}/managers", response_model=ManagerResponse)
def add_manager(
    caller: Manager, team_id: PositiveId, data: EmployeeAssignment, settings: AppSettings
) -> ManagerResponse:
    return service.assign_manager(caller, team_id, data.employee_id, settings)


@router.delete("/{team_id}/managers/{employee_id}", response_model=MessageResponse)
def remove_manager(
    caller: Manager, team_id: PositiveId, employee_id: PositiveId
) -> MessageResponse:
    return service.remove_manager(caller, team_id, employee_id)


@router.get("/{team_id}/locations", response_model=PageResponse[LocationResponse])
def locations(
    caller: Manager, team_id: PositiveId, query: Annotated[PageQuery, Query()]
) -> PageResponse[LocationResponse]:
    return service.list_locations(caller, team_id, query)


@router.post("/{team_id}/locations", response_model=LocationResponse)
def add_location(
    caller: Manager, team_id: PositiveId, data: LocationAssignment
) -> LocationResponse:
    return service.link_location(caller, team_id, data.work_location_id)


@router.delete("/{team_id}/locations/{location_id}", response_model=MessageResponse)
def remove_location(
    caller: Manager, team_id: PositiveId, location_id: PositiveId
) -> MessageResponse:
    return service.unlink_location(caller, team_id, location_id)

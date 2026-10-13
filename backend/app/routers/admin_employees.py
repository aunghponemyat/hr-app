from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.deps.auth import AppSettings
from app.deps.authz import AuthorizationContext, require_permission
from app.schemas.admin import (
    EmployeeCreate,
    EmployeeCreated,
    EmployeeQuery,
    EmployeeResponse,
    EmployeeUpdate,
    PageQuery,
    PageResponse,
    PasswordRequest,
    PasswordResponse,
    PositiveId,
    RoleResponse,
)
from app.services import employee_service as service

router = APIRouter(prefix="/api/v1/admin", tags=["employee administration"])
Reader = Annotated[
    AuthorizationContext,
    Depends(require_permission("employee", "read", allowed_scopes=frozenset({"any"}))),
]
Creator = Annotated[
    AuthorizationContext,
    Depends(require_permission("employee", "create", allowed_scopes=frozenset({"any"}))),
]
Updater = Annotated[
    AuthorizationContext,
    Depends(require_permission("employee", "update", allowed_scopes=frozenset({"any"}))),
]


@router.get("/employees", response_model=PageResponse[EmployeeResponse])
def employees(
    caller: Reader, query: Annotated[EmployeeQuery, Query()], settings: AppSettings
) -> PageResponse[EmployeeResponse]:
    return service.list_employees(caller, query, settings)


@router.post("/employees", response_model=EmployeeCreated, status_code=201)
def create(caller: Creator, data: EmployeeCreate, settings: AppSettings) -> EmployeeCreated:
    return service.create_employee(caller, data, settings)


@router.get("/employees/{employee_id}", response_model=EmployeeResponse)
def detail(caller: Reader, employee_id: PositiveId, settings: AppSettings) -> EmployeeResponse:
    return service.get_employee(caller, employee_id, settings)


@router.patch("/employees/{employee_id}", response_model=EmployeeResponse)
def update(
    caller: Updater, employee_id: PositiveId, data: EmployeeUpdate, settings: AppSettings
) -> EmployeeResponse:
    return service.update_employee(caller, employee_id, data, settings)


@router.post("/employees/{employee_id}/reset-password", response_model=PasswordResponse)
def reset(caller: Updater, employee_id: PositiveId, data: PasswordRequest) -> PasswordResponse:
    return service.reset_password(caller, employee_id, data)


@router.get("/utils/generate-password", response_model=PasswordResponse)
def password(caller: Creator) -> PasswordResponse:
    return service.generate_password(caller)


@router.get("/roles", response_model=PageResponse[RoleResponse])
def roles(caller: Reader, query: Annotated[PageQuery, Query()]) -> PageResponse[RoleResponse]:
    return service.list_roles(caller, query)

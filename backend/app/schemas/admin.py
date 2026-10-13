from datetime import datetime
from decimal import Decimal
from typing import Annotated, ClassVar, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from app.core.security import validate_password
from app.schemas.auth import RoleSummary, TeamSummary
from app.schemas.common import RequestSchema

PositiveId = Annotated[int, Field(gt=0, le=2**64 - 1)]
Name = Annotated[str, Field(min_length=1, max_length=100, pattern=r"\S")]
T = TypeVar("T")


class PageQuery(RequestSchema):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=25, ge=1, le=100)


class EmployeeQuery(PageQuery):
    search: str | None = Field(default=None, max_length=100)
    team_id: PositiveId | None = None
    role_id: PositiveId | None = None
    is_active: bool | None = None


class PageResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class PatchSchema(RequestSchema):
    nullable_fields: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def validate_patch(self) -> "PatchSchema":
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update.")
        for name in self.model_fields_set - self.nullable_fields:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null.")
        return self


class PasswordRequest(RequestSchema):
    default_password: SecretStr = Field(
        min_length=8,
        max_length=1024,
        repr=False,
        description="8–1024 characters containing letters and digits.",
    )

    @field_validator("default_password")
    @classmethod
    def password_policy(cls, value: SecretStr) -> SecretStr:
        validate_password(value.get_secret_value())
        return value


class EmployeeCreate(PasswordRequest):
    first_name: Name
    last_name: Name
    display_name: Name | None = None
    position: Name | None = None
    department: Name | None = None
    role_id: PositiveId
    team_id: PositiveId | None = None


class EmployeeUpdate(PatchSchema):
    nullable_fields = frozenset({"display_name", "position", "department", "team_id"})
    first_name: Name | None = None
    last_name: Name | None = None
    display_name: Name | None = None
    position: Name | None = None
    department: Name | None = None
    role_id: PositiveId | None = None
    team_id: PositiveId | None = None
    is_active: bool | None = None


class EmployeeResponse(BaseModel):
    id: int
    employee_id: str
    first_name: str
    last_name: str
    display_name: str | None
    position: str | None
    department: str | None
    role: RoleSummary
    team: TeamSummary | None
    is_active: bool
    must_change_password: bool
    created_at: datetime
    updated_at: datetime


class EmployeeCreated(EmployeeResponse):
    default_password: str = Field(repr=False)


class PasswordResponse(BaseModel):
    default_password: str = Field(repr=False)


class RoleResponse(RoleSummary):
    description: str | None
    permissions: list[str]


class TeamCreate(RequestSchema):
    name: Name
    description: str | None = Field(default=None, max_length=5000)


class TeamUpdate(PatchSchema):
    nullable_fields = frozenset({"description"})
    name: Name | None = None
    description: str | None = Field(default=None, max_length=5000)


class TeamResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: str | None


class EmployeeAssignment(RequestSchema):
    employee_id: PositiveId


class LocationAssignment(RequestSchema):
    work_location_id: PositiveId


class ManagerResponse(BaseModel):
    employee: EmployeeResponse
    assigned_at: datetime


class LocationCreate(RequestSchema):
    name: Name
    latitude: Decimal = Field(ge=-90, le=90, decimal_places=6)
    longitude: Decimal = Field(ge=-180, le=180, decimal_places=6)
    allowed_radius_m: int = Field(default=100, ge=50, le=100)


class LocationUpdate(PatchSchema):
    name: Name | None = None
    latitude: Decimal | None = Field(default=None, ge=-90, le=90, decimal_places=6)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180, decimal_places=6)
    allowed_radius_m: int | None = Field(default=None, ge=50, le=100)


class LocationResponse(LocationCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


class TeamMemberResponse(EmployeeResponse):
    today_status: str | None


class ProfileUpdate(PatchSchema):
    nullable_fields = frozenset({"display_name"})
    display_name: Name | None = None

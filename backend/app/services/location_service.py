from sqlalchemy import delete, select

from app.core.errors import AppError
from app.models import Attendance, TeamWorkLocation, WorkLocation
from app.schemas.admin import (
    LocationCreate,
    LocationResponse,
    LocationUpdate,
    PageQuery,
    PageResponse,
)
from app.schemas.auth import MessageResponse
from app.services.admin_support import audit, get_entity, mutation, page_rows, require_any
from app.services.authorization_service import AuthorizationContext


def list_locations(
    caller: AuthorizationContext, query: PageQuery
) -> PageResponse[LocationResponse]:
    require_any(caller, "location", "manage")
    rows, total = page_rows(caller.session, select(WorkLocation).order_by(WorkLocation.id), query)
    return PageResponse(
        items=[LocationResponse.model_validate(row) for row in rows],
        total=total,
        page=query.page,
        page_size=query.page_size,
    )


def get_location(caller: AuthorizationContext, location_id: int) -> LocationResponse:
    require_any(caller, "location", "manage")
    return LocationResponse.model_validate(get_entity(caller.session, WorkLocation, location_id))


def create_location(caller: AuthorizationContext, data: LocationCreate) -> LocationResponse:
    with mutation(caller, "location", "manage"):
        location = WorkLocation(**data.model_dump())
        caller.session.add(location)
        caller.session.flush()
        response = LocationResponse.model_validate(location)
        audit(
            caller,
            "location.create",
            "work_location",
            location.id,
            after=response.model_dump(mode="json"),
        )
        return response


def update_location(
    caller: AuthorizationContext, location_id: int, data: LocationUpdate
) -> LocationResponse:
    with mutation(caller, "location", "manage"):
        location = get_entity(caller.session, WorkLocation, location_id, lock=True)
        before = LocationResponse.model_validate(location).model_dump(mode="json")
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(location, field, value)
        caller.session.flush()
        response = LocationResponse.model_validate(location)
        audit(
            caller,
            "location.update",
            "work_location",
            location.id,
            before,
            response.model_dump(mode="json"),
        )
        return response


def delete_location(caller: AuthorizationContext, location_id: int) -> MessageResponse:
    with mutation(caller, "location", "manage"):
        location = get_entity(caller.session, WorkLocation, location_id, lock=True)
        linked = caller.session.scalar(
            select(TeamWorkLocation.team_id)
            .where(TeamWorkLocation.work_location_id == location_id)
            .limit(1)
        )
        used = caller.session.scalar(
            select(Attendance.id).where(Attendance.work_location_id == location_id).limit(1)
        )
        if linked is not None or used is not None:
            raise AppError(
                409, "LOCATION_IN_USE", "This location is linked to a team or used by attendance."
            )
        audit(
            caller,
            "location.delete",
            "work_location",
            location.id,
            before=LocationResponse.model_validate(location).model_dump(mode="json"),
        )
        caller.session.execute(delete(WorkLocation).where(WorkLocation.id == location_id))
        return MessageResponse(message="Work location deleted.")

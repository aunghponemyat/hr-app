from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.orm import joinedload

from app.core.config import Settings
from app.core.errors import AppError
from app.models import Employee, Team, TeamManager, TeamMember, TeamWorkLocation, WorkLocation
from app.schemas.admin import (
    EmployeeResponse,
    LocationResponse,
    ManagerResponse,
    PageQuery,
    PageResponse,
    TeamCreate,
    TeamResponse,
    TeamUpdate,
)
from app.schemas.auth import MessageResponse
from app.services.admin_support import (
    audit,
    employee_response,
    get_entity,
    mutation,
    page_rows,
    require_any,
)
from app.services.authorization_service import AuthorizationContext
from app.services.membership_service import manager_eligible, move_employee, validate_assignee
from app.utils.time import utc_now


def list_teams(caller: AuthorizationContext, query: PageQuery) -> PageResponse[TeamResponse]:
    require_any(caller, "team", "manage")
    rows, total = page_rows(caller.session, select(Team).order_by(Team.id), query)
    return PageResponse(
        items=[TeamResponse.model_validate(row) for row in rows],
        total=total,
        page=query.page,
        page_size=query.page_size,
    )


def get_team(caller: AuthorizationContext, team_id: int) -> TeamResponse:
    require_any(caller, "team", "manage")
    return TeamResponse.model_validate(get_entity(caller.session, Team, team_id))


def create_team(caller: AuthorizationContext, data: TeamCreate) -> TeamResponse:
    with mutation(caller, "team", "manage"):
        team = Team(**data.model_dump())
        caller.session.add(team)
        caller.session.flush()
        response = TeamResponse.model_validate(team)
        audit(caller, "team.create", "team", team.id, after=response.model_dump(mode="json"))
        return response


def update_team(caller: AuthorizationContext, team_id: int, data: TeamUpdate) -> TeamResponse:
    with mutation(caller, "team", "manage"):
        team = get_entity(caller.session, Team, team_id, lock=True)
        before = TeamResponse.model_validate(team).model_dump(mode="json")
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(team, field, value)
        caller.session.flush()
        response = TeamResponse.model_validate(team)
        audit(caller, "team.update", "team", team.id, before, response.model_dump(mode="json"))
        return response


def delete_team(caller: AuthorizationContext, team_id: int) -> MessageResponse:
    with mutation(caller, "team", "manage"):
        team = get_entity(caller.session, Team, team_id, lock=True)
        references = (
            select(Employee.id).where(Employee.team_id == team_id),
            select(TeamMember.employee_id).where(TeamMember.team_id == team_id),
            select(TeamManager.employee_id).where(TeamManager.team_id == team_id),
            select(TeamWorkLocation.work_location_id).where(TeamWorkLocation.team_id == team_id),
        )
        if any(caller.session.scalar(stmt.limit(1)) is not None for stmt in references):
            raise AppError(
                409, "TEAM_IN_USE", "This team has members, history, or linked locations."
            )
        audit(
            caller,
            "team.delete",
            "team",
            team.id,
            before=TeamResponse.model_validate(team).model_dump(mode="json"),
        )
        caller.session.execute(delete(Team).where(Team.id == team_id))
        return MessageResponse(message="Team deleted.")


def list_members(
    caller: AuthorizationContext, team_id: int, query: PageQuery, settings: Settings
) -> PageResponse[EmployeeResponse]:
    require_any(caller, "team", "manage")
    get_entity(caller.session, Team, team_id)
    rows, total = page_rows(
        caller.session,
        select(Employee)
        .where(Employee.team_id == team_id)
        .options(joinedload(Employee.role), joinedload(Employee.team))
        .order_by(Employee.id),
        query,
    )
    return PageResponse(
        items=[employee_response(row, settings) for row in rows],
        total=total,
        page=query.page,
        page_size=query.page_size,
    )


def assign_member(
    caller: AuthorizationContext, team_id: int, employee_id: int, settings: Settings
) -> EmployeeResponse:
    with mutation(caller, "team", "manage"):
        employee = get_entity(caller.session, Employee, employee_id, lock=True)
        validate_assignee(employee)
        move_employee(caller, employee, team_id)
        caller.session.flush()
        caller.session.refresh(employee)
        return employee_response(employee, settings)


def remove_member(caller: AuthorizationContext, team_id: int, employee_id: int) -> MessageResponse:
    with mutation(caller, "team", "manage"):
        get_entity(caller.session, Team, team_id, lock=True)
        employee = get_entity(caller.session, Employee, employee_id, lock=True)
        if employee.team_id != team_id:
            raise AppError(404, "NOT_FOUND", "Member not found in this team.")
        move_employee(caller, employee, None)
        return MessageResponse(message="Member removed from team.")


def list_managers(
    caller: AuthorizationContext, team_id: int, query: PageQuery, settings: Settings
) -> PageResponse[ManagerResponse]:
    require_any(caller, "team", "manage")
    get_entity(caller.session, Team, team_id)
    rows, total = page_rows(
        caller.session,
        select(TeamManager)
        .where(
            TeamManager.team_id == team_id,
            TeamManager.removed_at.is_(None),
        )
        .options(
            joinedload(TeamManager.employee).joinedload(Employee.role),
            joinedload(TeamManager.employee).joinedload(Employee.team),
        )
        .order_by(TeamManager.employee_id, TeamManager.assigned_at),
        query,
    )
    return PageResponse(
        items=[
            ManagerResponse(
                employee=employee_response(row.employee, settings),
                assigned_at=row.assigned_at.astimezone(ZoneInfo(settings.app_timezone)),
            )
            for row in rows
        ],
        total=total,
        page=query.page,
        page_size=query.page_size,
    )


def assign_manager(
    caller: AuthorizationContext, team_id: int, employee_id: int, settings: Settings
) -> ManagerResponse:
    with mutation(caller, "team", "manage"):
        get_entity(caller.session, Team, team_id, lock=True)
        employee = get_entity(caller.session, Employee, employee_id, lock=True)
        if not manager_eligible(caller, employee):
            raise AppError(
                422,
                "INELIGIBLE_MANAGER",
                "Manager must be active and hold team/any attendance read permission.",
            )
        assignment = caller.session.scalar(
            select(TeamManager)
            .where(
                TeamManager.team_id == team_id,
                TeamManager.employee_id == employee_id,
                TeamManager.removed_at.is_(None),
            )
            .with_for_update()
        )
        if assignment is None:
            assignment = TeamManager(
                team_id=team_id, employee_id=employee_id, assigned_at=utc_now()
            )
            caller.session.add(assignment)
            caller.session.flush()
            audit(
                caller,
                "team.manager_assign",
                "team",
                team_id,
                after={
                    "employee_id": employee_id,
                    "assigned_at": assignment.assigned_at.isoformat(),
                },
            )
        return ManagerResponse(
            employee=employee_response(employee, settings),
            assigned_at=assignment.assigned_at.astimezone(ZoneInfo(settings.app_timezone)),
        )


def remove_manager(caller: AuthorizationContext, team_id: int, employee_id: int) -> MessageResponse:
    with mutation(caller, "team", "manage"):
        get_entity(caller.session, Team, team_id, lock=True)
        assignment = caller.session.scalar(
            select(TeamManager)
            .where(
                TeamManager.team_id == team_id,
                TeamManager.employee_id == employee_id,
                TeamManager.removed_at.is_(None),
            )
            .with_for_update()
        )
        if assignment is None:
            raise AppError(404, "NOT_FOUND", "Active manager assignment not found.")
        assignment.removed_at = utc_now()
        audit(
            caller,
            "team.manager_remove",
            "team",
            team_id,
            {"employee_id": employee_id},
            {"removed_at": assignment.removed_at.isoformat()},
        )
        return MessageResponse(message="Manager assignment removed.")


def list_locations(
    caller: AuthorizationContext, team_id: int, query: PageQuery
) -> PageResponse[LocationResponse]:
    require_any(caller, "team", "manage")
    get_entity(caller.session, Team, team_id)
    rows, total = page_rows(
        caller.session,
        select(WorkLocation)
        .join(TeamWorkLocation, TeamWorkLocation.work_location_id == WorkLocation.id)
        .where(TeamWorkLocation.team_id == team_id)
        .order_by(WorkLocation.id),
        query,
    )
    return PageResponse(
        items=[LocationResponse.model_validate(row) for row in rows],
        total=total,
        page=query.page,
        page_size=query.page_size,
    )


def link_location(caller: AuthorizationContext, team_id: int, location_id: int) -> LocationResponse:
    with mutation(caller, "team", "manage"):
        get_entity(caller.session, Team, team_id, lock=True)
        location = get_entity(caller.session, WorkLocation, location_id, lock=True)
        if caller.session.get(TeamWorkLocation, (team_id, location_id)) is None:
            caller.session.add(TeamWorkLocation(team_id=team_id, work_location_id=location_id))
            audit(
                caller,
                "team.location_link",
                "team",
                team_id,
                after={"work_location_id": location_id},
            )
        return LocationResponse.model_validate(location)


def unlink_location(
    caller: AuthorizationContext, team_id: int, location_id: int
) -> MessageResponse:
    with mutation(caller, "team", "manage"):
        get_entity(caller.session, Team, team_id, lock=True)
        link = caller.session.get(TeamWorkLocation, (team_id, location_id))
        if link is None:
            raise AppError(404, "NOT_FOUND", "Linked location not found.")
        caller.session.delete(link)
        audit(
            caller,
            "team.location_unlink",
            "team",
            team_id,
            before={"work_location_id": location_id},
        )
        return MessageResponse(message="Work location unlinked.")

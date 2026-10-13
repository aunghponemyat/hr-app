from app.models import Employee
from app.schemas.admin import ProfileUpdate
from app.schemas.auth import ProfileResponse, RoleSummary, TeamSummary
from app.services.admin_support import get_entity
from app.services.authorization_service import AuthorizationContext, authorize


def get_profile(caller: AuthorizationContext) -> ProfileResponse:
    authorize(caller, "profile", "read", caller.employee)
    return profile_response(caller)


def profile_response(caller: AuthorizationContext) -> ProfileResponse:
    employee = caller.employee
    permissions = sorted(permission.code for permission in caller.permissions)
    return ProfileResponse(
        id=employee.id,
        employee_id=employee.employee_id,
        first_name=employee.first_name,
        last_name=employee.last_name,
        display_name=employee.display_name,
        position=employee.position,
        department=employee.department,
        role=RoleSummary(id=employee.role.id, name=employee.role.name),
        team=TeamSummary(id=employee.team.id, name=employee.team.name) if employee.team else None,
        permissions=permissions,
        must_change_password=employee.must_change_password,
    )


def update_profile(caller: AuthorizationContext, data: ProfileUpdate) -> ProfileResponse:
    authorize(caller, "profile", "update", caller.employee)
    session = caller.session
    try:
        employee = get_entity(session, Employee, caller.employee.id, lock=True)
        employee.display_name = data.display_name
        session.flush()
        response = profile_response(caller)
        session.commit()
        return response
    except Exception:
        session.rollback()
        raise

from app.schemas.auth import ProfileResponse, RoleSummary, TeamSummary
from app.services.authorization_service import AuthorizationContext, authorize


def get_profile(caller: AuthorizationContext) -> ProfileResponse:
    employee = caller.employee
    authorize(caller, "profile", "read", employee)
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

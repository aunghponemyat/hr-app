from app.core.errors import AppError
from app.models import Employee
from app.schemas.auth import ProfileResponse, RoleSummary, TeamSummary


def get_profile(employee: Employee) -> ProfileResponse:
    permissions = sorted(permission.code for permission in employee.role.permissions)
    if "profile.read.self" not in permissions:
        raise AppError(403, "PERMISSION_DENIED", "Permission denied.")
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

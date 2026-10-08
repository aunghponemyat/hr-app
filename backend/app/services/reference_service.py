from sqlalchemy import delete, select
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.orm import Session

from app.models import IdSequence, LeaveReason, LeaveType, Permission, Role, RolePermission

PERMISSION_CODES = (
    "profile.read.self",
    "profile.update.self",
    "attendance.create.self",
    "attendance.read.self",
    "attendance.read.team",
    "attendance.read.any",
    "attendance.update.team",
    "attendance.update.any",
    "leave.create.self",
    "leave.read.self",
    "leave.read.team",
    "leave.read.any",
    "leave.decide.team",
    "leave.decide.any",
    "employee.read.team",
    "employee.read.any",
    "employee.create.any",
    "employee.update.any",
    "team.manage.any",
    "location.manage.any",
    "report.export.self",
    "report.export.any",
)
SELF_PERMISSIONS = frozenset(code for code in PERMISSION_CODES if code.endswith(".self"))
TEAM_PERMISSIONS = frozenset(code for code in PERMISSION_CODES if code.endswith(".team"))
ANY_PERMISSIONS = frozenset(code for code in PERMISSION_CODES if code.endswith(".any"))
ROLE_PERMISSIONS = {
    "employee": SELF_PERMISSIONS,
    "senior_staff": SELF_PERMISSIONS,
    "reporting_manager": SELF_PERMISSIONS | TEAM_PERMISSIONS,
    "hr": SELF_PERMISSIONS | ANY_PERMISSIONS,
    "c_level": SELF_PERMISSIONS | ANY_PERMISSIONS,
}
LEAVE_TYPES = {
    "annual": "Annual leave",
    "sick": "Sick leave",
    "personal": "Personal leave",
    "maternity": "Maternity leave",
    "paternity": "Paternity leave",
    "unpaid": "Unpaid leave",
    "other": "Other",
}
LEAVE_REASONS = {
    "vacation": "Vacation",
    "medical": "Medical",
    "family_emergency": "Family emergency",
    "personal_errand": "Personal errand",
    "childcare": "Childcare",
    "other": "Other",
}


def seed_reference_data(session: Session) -> None:
    """Reconcile the seeded reference data inside the caller's transaction."""
    session.flush()
    for code in PERMISSION_CODES:
        resource, action, scope = code.split(".")
        statement = insert(Permission).values(
            code=code, resource=resource, action=action, scope=scope
        )
        session.execute(
            statement.on_duplicate_key_update(resource=resource, action=action, scope=scope)
        )

    permission_ids = dict(session.execute(select(Permission.code, Permission.id)).tuples().all())
    for role_name, codes in ROLE_PERMISSIONS.items():
        statement = insert(Role).values(name=role_name)
        session.execute(statement.on_duplicate_key_update(name=role_name))
        role_id = session.execute(select(Role.id).where(Role.name == role_name)).scalar_one()
        desired_ids = [permission_ids[code] for code in sorted(codes)]
        session.execute(
            delete(RolePermission).where(
                RolePermission.role_id == role_id,
                RolePermission.permission_id.not_in(desired_ids),
            )
        )
        for permission_id in desired_ids:
            grant = insert(RolePermission).values(role_id=role_id, permission_id=permission_id)
            session.execute(grant.on_duplicate_key_update(role_id=role_id))

    for code, name in LEAVE_TYPES.items():
        leave_type = insert(LeaveType).values(code=code, name=name, is_active=True)
        session.execute(leave_type.on_duplicate_key_update(name=name))

    for code, name in LEAVE_REASONS.items():
        reason = insert(LeaveReason).values(
            code=code, name=name, requires_text=code == "other", is_active=True
        )
        session.execute(reason.on_duplicate_key_update(name=name, requires_text=code == "other"))

    sequence = insert(IdSequence).values(name="employee_id", next_value=1)
    # A repeat seed must never rewind an employee ID sequence that has already advanced.
    session.execute(sequence.on_duplicate_key_update(name="employee_id"))
    session.expire_all()

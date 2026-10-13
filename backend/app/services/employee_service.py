import secrets
import string

from sqlalchemy import or_, select, update
from sqlalchemy.orm import joinedload

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import hash_password
from app.models import Employee, Permission, RefreshSession, Role, RolePermission
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
    RoleResponse,
)
from app.services.admin_support import (
    audit,
    employee_response,
    get_entity,
    mutation,
    page_rows,
    require_any,
)
from app.services.authorization_service import AuthorizationContext, load_permissions
from app.services.id_service import generate_employee_id
from app.services.membership_service import close_manager_assignments, move_employee
from app.utils.time import utc_now


def list_employees(
    caller: AuthorizationContext,
    query: EmployeeQuery,
    settings: Settings,
) -> PageResponse[EmployeeResponse]:
    require_any(caller, "employee", "read")
    stmt = select(Employee).options(joinedload(Employee.role), joinedload(Employee.team))
    if query.search is not None:
        stmt = stmt.where(
            or_(
                *(
                    column.contains(query.search, autoescape=True)
                    for column in (
                        Employee.employee_id,
                        Employee.first_name,
                        Employee.last_name,
                        Employee.display_name,
                    )
                )
            )
        )
    for field in ("team_id", "role_id", "is_active"):
        value = getattr(query, field)
        if value is not None:
            stmt = stmt.where(getattr(Employee, field) == value)
    rows, total = page_rows(caller.session, stmt.order_by(Employee.id), query)
    return PageResponse(
        items=[employee_response(row, settings) for row in rows],
        total=total,
        page=query.page,
        page_size=query.page_size,
    )


def get_employee(
    caller: AuthorizationContext, employee_id: int, settings: Settings
) -> EmployeeResponse:
    require_any(caller, "employee", "read")
    return employee_response(get_entity(caller.session, Employee, employee_id), settings)


def create_employee(
    caller: AuthorizationContext,
    data: EmployeeCreate,
    settings: Settings,
) -> EmployeeCreated:
    require_any(caller, "employee", "create")
    password_hash = hash_password(data.default_password.get_secret_value())
    with mutation(caller, "employee", "create"):
        get_entity(caller.session, Role, data.role_id)
        employee = Employee(
            employee_id=generate_employee_id(caller.session, settings),
            password_hash=password_hash,
            role_id=data.role_id,
            **data.model_dump(exclude={"default_password", "role_id", "team_id"}),
        )
        caller.session.add(employee)
        caller.session.flush()
        move_employee(caller, employee, data.team_id)
        caller.session.refresh(employee)
        response = employee_response(employee, settings)
        audit(
            caller,
            "employee.create",
            "employee",
            employee.id,
            after=response.model_dump(mode="json"),
        )
        return EmployeeCreated(
            **response.model_dump(), default_password=data.default_password.get_secret_value()
        )


def protect_last_admin(
    caller: AuthorizationContext, employee: Employee, data: EmployeeUpdate
) -> None:
    new_role = data.role_id if data.role_id is not None else employee.role_id
    new_active = data.is_active if data.is_active is not None else employee.is_active
    if not employee.is_active or not any(
        grant.code == "employee.create.any"
        for grant in load_permissions(caller.session, employee.role_id)
    ):
        return
    if new_active and any(
        grant.code == "employee.create.any" for grant in load_permissions(caller.session, new_role)
    ):
        return
    # Locking reads see preceding commits even under MySQL REPEATABLE READ.
    others = caller.session.scalars(
        select(Employee)
        .join(RolePermission, RolePermission.role_id == Employee.role_id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(
            Employee.is_active.is_(True),
            Employee.id != employee.id,
            Permission.code == "employee.create.any",
            Permission.resource == "employee",
            Permission.action == "create",
            Permission.scope == "any",
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    if not others:
        raise AppError(409, "LAST_ADMIN", "The final active administrator must be retained.")


def update_employee(
    caller: AuthorizationContext,
    employee_id: int,
    data: EmployeeUpdate,
    settings: Settings,
) -> EmployeeResponse:
    with mutation(caller, "employee", "update"):
        employee = get_entity(caller.session, Employee, employee_id, lock=True)
        before = employee_response(employee, settings).model_dump(mode="json")
        if data.role_id is not None:
            get_entity(caller.session, Role, data.role_id)
        protect_last_admin(caller, employee, data)
        if "team_id" in data.model_fields_set:
            move_employee(caller, employee, data.team_id)
        for field, value in data.model_dump(exclude_unset=True, exclude={"team_id"}).items():
            setattr(employee, field, value)
        caller.session.flush()
        close_manager_assignments(caller, employee)
        if data.is_active is False:
            revoke_sessions(caller, employee.id)
        caller.session.flush()
        caller.session.refresh(employee)
        response = employee_response(employee, settings)
        audit(
            caller,
            "employee.update",
            "employee",
            employee.id,
            before,
            response.model_dump(mode="json"),
        )
        return response


def revoke_sessions(caller: AuthorizationContext, employee_id: int) -> None:
    caller.session.execute(
        update(RefreshSession)
        .where(
            RefreshSession.employee_id == employee_id,
            RefreshSession.revoked_at.is_(None),
        )
        .values(revoked_at=utc_now())
    )


def reset_password(
    caller: AuthorizationContext, employee_id: int, data: PasswordRequest
) -> PasswordResponse:
    require_any(caller, "employee", "update")
    password_hash = hash_password(data.default_password.get_secret_value())
    with mutation(caller, "employee", "update"):
        employee = get_entity(caller.session, Employee, employee_id, lock=True)
        employee.password_hash = password_hash
        employee.must_change_password = True
        employee.password_changed_at = utc_now()
        employee.failed_login_count = 0
        employee.locked_until = None
        revoke_sessions(caller, employee.id)
        audit(
            caller,
            "employee.password_reset",
            "employee",
            employee.id,
            after={"must_change_password": True, "sessions_revoked": True},
        )
        return PasswordResponse(default_password=data.default_password.get_secret_value())


def generate_password(caller: AuthorizationContext) -> PasswordResponse:
    require_any(caller, "employee", "create")
    alphabet = string.ascii_letters + string.digits + "!#%*?"
    while True:
        value = "".join(secrets.choice(alphabet) for _ in range(12))
        if any(char.isalpha() for char in value) and any(char.isdigit() for char in value):
            return PasswordResponse(default_password=value)


def list_roles(caller: AuthorizationContext, query: PageQuery) -> PageResponse[RoleResponse]:
    require_any(caller, "employee", "read")
    rows, total = page_rows(caller.session, select(Role).order_by(Role.id), query)
    return PageResponse(
        items=[
            RoleResponse(
                id=role.id,
                name=role.name,
                description=role.description,
                permissions=sorted(
                    grant.code for grant in load_permissions(caller.session, role.id)
                ),
            )
            for role in rows
        ],
        total=total,
        page=query.page,
        page_size=query.page_size,
    )

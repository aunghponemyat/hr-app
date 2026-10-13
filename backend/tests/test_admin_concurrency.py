from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.models import AuditLog, Employee, Role
from app.schemas.admin import EmployeeCreate, EmployeeUpdate
from app.services.authorization_service import AuthorizationContext, load_permissions
from app.services.employee_service import create_employee, update_employee
from app.services.reference_service import seed_reference_data


def test_concurrent_admin_demotions_retain_one_active_admin(
    db_engine: Engine, auth_settings: Settings
) -> None:
    with Session(db_engine) as session, session.begin():
        seed_reference_data(session)
        admin_role = session.scalar(select(Role.id).where(Role.name == "hr"))
        employee_role = session.scalar(select(Role.id).where(Role.name == "employee"))
        assert admin_role is not None and employee_role is not None
        admins = [
            Employee(
                employee_id=f"RACE{uuid4().hex[:12]}",
                role_id=admin_role,
                first_name="Concurrent",
                last_name="Admin",
                password_hash="$argon2id$test-fixture",
                must_change_password=False,
            )
            for _ in range(2)
        ]
        session.add_all(admins)
        session.flush()
        admin_ids = [admin.id for admin in admins]
    barrier = Barrier(2)

    def worker(employee_id: int) -> str:
        with Session(db_engine) as session:
            employee = session.get(Employee, employee_id)
            assert employee is not None
            caller = AuthorizationContext(
                employee, session, load_permissions(session, employee.role_id)
            )
            barrier.wait(timeout=10)
            try:
                update_employee(
                    caller, employee_id, EmployeeUpdate(role_id=employee_role), auth_settings
                )
                return "updated"
            except AppError as error:
                return error.code

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(worker, admin_ids))
        assert sorted(results) == ["LAST_ADMIN", "updated"]
        with Session(db_engine) as session:
            remaining = session.scalars(
                select(Employee).where(
                    Employee.id.in_(admin_ids),
                    Employee.role_id == admin_role,
                    Employee.is_active.is_(True),
                )
            ).all()
            assert len(remaining) == 1
    finally:
        with Session(db_engine) as session, session.begin():
            session.execute(delete(AuditLog).where(AuditLog.actor_id.in_(admin_ids)))
            session.execute(delete(Employee).where(Employee.id.in_(admin_ids)))


def test_concurrent_employee_creation_service_issues_unique_ids(
    db_engine: Engine, auth_settings: Settings
) -> None:
    with Session(db_engine) as session, session.begin():
        seed_reference_data(session)
        admin_role = session.scalar(select(Role.id).where(Role.name == "hr"))
        employee_role = session.scalar(select(Role.id).where(Role.name == "employee"))
        assert admin_role is not None and employee_role is not None
        admin = Employee(
            employee_id=f"ADMIN{uuid4().hex[:12]}",
            role_id=admin_role,
            first_name="Concurrent",
            last_name="Admin",
            password_hash="$argon2id$test-fixture",
            must_change_password=False,
        )
        session.add(admin)
        session.flush()
        admin_id = admin.id

    def worker(_index: int) -> tuple[int, str]:
        with Session(db_engine) as session:
            employee = session.get(Employee, admin_id)
            assert employee is not None
            caller = AuthorizationContext(
                employee, session, load_permissions(session, employee.role_id)
            )
            response = create_employee(
                caller,
                EmployeeCreate(
                    first_name="Concurrent",
                    last_name="Employee",
                    role_id=employee_role,
                    default_password="InitialPass123",
                ),
                auth_settings,
            )
            return response.id, response.employee_id

    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(worker, range(4)))
        assert len({business_id for _id, business_id in results}) == 4
        assert len({internal_id for internal_id, _id in results}) == 4
    finally:
        with Session(db_engine) as session, session.begin():
            created_ids = select(AuditLog.entity_id).where(
                AuditLog.actor_id == admin_id, AuditLog.action == "employee.create"
            )
            employee_ids = list(session.scalars(created_ids))
            session.execute(delete(AuditLog).where(AuditLog.actor_id == admin_id))
            session.execute(delete(Employee).where(Employee.id.in_(employee_ids + [admin_id])))

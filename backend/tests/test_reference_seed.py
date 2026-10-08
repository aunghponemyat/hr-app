from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.models import IdSequence, LeaveReason, LeaveType, Permission, Role, RolePermission
from app.services.reference_service import seed_reference_data

EXPECTED_SELF = {
    "profile.read.self",
    "profile.update.self",
    "attendance.create.self",
    "attendance.read.self",
    "leave.create.self",
    "leave.read.self",
    "report.export.self",
}
EXPECTED_TEAM = {
    "attendance.read.team",
    "attendance.update.team",
    "leave.read.team",
    "leave.decide.team",
    "employee.read.team",
}
EXPECTED_ANY = {
    "attendance.read.any",
    "attendance.update.any",
    "leave.read.any",
    "leave.decide.any",
    "employee.read.any",
    "employee.create.any",
    "employee.update.any",
    "team.manage.any",
    "location.manage.any",
    "report.export.any",
}


def reference_counts(session: Session) -> tuple[int, ...]:
    return tuple(
        session.execute(select(func.count()).select_from(model)).scalar_one()
        for model in (Role, Permission, RolePermission, LeaveType, LeaveReason, IdSequence)
    )


def test_seed_twice_preserves_ids_counts_and_sequence(db_session: Session) -> None:
    seed_reference_data(db_session)
    first_ids = dict(db_session.execute(select(Role.name, Role.id)).tuples().all())
    db_session.execute(
        update(IdSequence).where(IdSequence.name == "employee_id").values(next_value=42)
    )
    seed_reference_data(db_session)
    assert reference_counts(db_session) == (5, 22, 60, 7, 6, 1)
    assert dict(db_session.execute(select(Role.name, Role.id)).tuples().all()) == first_ids
    sequence = db_session.get(IdSequence, "employee_id")
    assert sequence is not None and sequence.next_value == 42


def test_exact_role_permission_mapping(seeded_session: Session) -> None:
    permissions = set(seeded_session.scalars(select(Permission.code)))
    assert permissions == EXPECTED_SELF | EXPECTED_TEAM | EXPECTED_ANY
    for role_name, expected in (
        ("employee", EXPECTED_SELF),
        ("senior_staff", EXPECTED_SELF),
        ("reporting_manager", EXPECTED_SELF | EXPECTED_TEAM),
        ("hr", EXPECTED_SELF | EXPECTED_ANY),
        ("c_level", EXPECTED_SELF | EXPECTED_ANY),
    ):
        role = seeded_session.execute(select(Role).where(Role.name == role_name)).scalar_one()
        assert {permission.code for permission in role.permissions} == expected
        assert all(p.code == f"{p.resource}.{p.action}.{p.scope}" for p in role.permissions)


def test_seed_restores_missing_grants_and_removes_unexpected_grants(
    seeded_session: Session,
) -> None:
    employee_role = seeded_session.execute(select(Role).where(Role.name == "employee")).scalar_one()
    admin_permission = seeded_session.execute(
        select(Permission).where(Permission.code == "employee.create.any")
    ).scalar_one()
    seeded_session.execute(delete(RolePermission).where(RolePermission.role_id == employee_role.id))
    seeded_session.add(RolePermission(role_id=employee_role.id, permission_id=admin_permission.id))
    seeded_session.flush()
    seed_reference_data(seeded_session)
    assert {permission.code for permission in employee_role.permissions} == EXPECTED_SELF


def test_leave_reference_values_and_deactivation_preserved(seeded_session: Session) -> None:
    assert set(seeded_session.scalars(select(LeaveType.code))) == {
        "annual",
        "sick",
        "personal",
        "maternity",
        "paternity",
        "unpaid",
        "other",
    }
    reasons = list(seeded_session.scalars(select(LeaveReason)))
    assert {reason.code for reason in reasons} == {
        "vacation",
        "medical",
        "family_emergency",
        "personal_errand",
        "childcare",
        "other",
    }
    assert {reason.code for reason in reasons if reason.requires_text} == {"other"}
    annual = seeded_session.execute(
        select(LeaveType).where(LeaveType.code == "annual")
    ).scalar_one()
    annual.is_active = False
    seeded_session.flush()
    seed_reference_data(seeded_session)
    assert not annual.is_active

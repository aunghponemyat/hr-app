"""initial HR schema

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Initial schema generated from the typed models, then reviewed for MySQL.
    op.create_table(
        "id_sequences",
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("next_value", mysql.BIGINT(unsigned=True), nullable=False),
        sa.CheckConstraint("next_value >= 1", name=op.f("ck_id_sequences_positive_next_value")),
        sa.PrimaryKeyConstraint("name", name=op.f("pk_id_sequences")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "leave_reasons",
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("requires_text", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_leave_reasons")),
        sa.UniqueConstraint("code", name=op.f("uq_leave_reasons_code")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "leave_types",
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_leave_types")),
        sa.UniqueConstraint("code", name=op.f("uq_leave_types_code")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "permissions",
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("resource", sa.String(length=50), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.CheckConstraint(
            "scope IN ('self', 'team', 'any')", name=op.f("ck_permissions_valid_scope")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_permissions")),
        sa.UniqueConstraint("code", name=op.f("uq_permissions_code")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "roles",
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_roles")),
        sa.UniqueConstraint("name", name=op.f("uq_roles_name")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "teams",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teams")),
        sa.UniqueConstraint("name", name=op.f("uq_teams_name")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "work_locations",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("latitude", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column("longitude", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column("allowed_radius_m", sa.Integer(), server_default=sa.text("100"), nullable=False),
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.CheckConstraint(
            "allowed_radius_m BETWEEN 50 AND 100", name=op.f("ck_work_locations_radius_range")
        ),
        sa.CheckConstraint(
            "latitude BETWEEN -90 AND 90", name=op.f("ck_work_locations_latitude_range")
        ),
        sa.CheckConstraint(
            "longitude BETWEEN -180 AND 180", name=op.f("ck_work_locations_longitude_range")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_work_locations")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "employees",
        sa.Column("employee_id", sa.String(length=20), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("team_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=True),
        sa.Column("position", sa.String(length=100), nullable=True),
        sa.Column("department", sa.String(length=100), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "must_change_password", sa.Boolean(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column("password_changed_at", mysql.TIMESTAMP(fsp=6), nullable=True),
        sa.Column("failed_login_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("locked_until", mysql.TIMESTAMP(fsp=6), nullable=True),
        sa.Column("last_login_at", mysql.TIMESTAMP(fsp=6), nullable=True),
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            mysql.TIMESTAMP(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            mysql.TIMESTAMP(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "failed_login_count >= 0", name=op.f("ck_employees_nonnegative_failed_logins")
        ),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], name=op.f("fk_employees_role_id_roles")),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], name=op.f("fk_employees_team_id_teams")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_employees")),
        sa.UniqueConstraint("employee_id", name=op.f("uq_employees_employee_id")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "role_permissions",
        sa.Column("role_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("permission_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            name=op.f("fk_role_permissions_permission_id_permissions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name=op.f("fk_role_permissions_role_id_roles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("role_id", "permission_id", name=op.f("pk_role_permissions")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "team_work_locations",
        sa.Column("team_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("work_location_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name=op.f("fk_team_work_locations_team_id_teams")
        ),
        sa.ForeignKeyConstraint(
            ["work_location_id"],
            ["work_locations.id"],
            name=op.f("fk_team_work_locations_work_location_id_work_locations"),
        ),
        sa.PrimaryKeyConstraint("team_id", "work_location_id", name=op.f("pk_team_work_locations")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "attendance",
        sa.Column("employee_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("attendance_date", sa.Date(), nullable=False),
        sa.Column("work_mode", sa.Enum("onsite", "remote", name="workmode"), nullable=False),
        sa.Column("work_location_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("clock_in", mysql.TIMESTAMP(fsp=6), nullable=True),
        sa.Column("clock_out", mysql.TIMESTAMP(fsp=6), nullable=True),
        sa.Column("clock_in_latitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("clock_in_longitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("clock_in_accuracy_m", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("clock_in_distance_m", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("clock_in_verified", sa.Boolean(), nullable=True),
        sa.Column("clock_out_latitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("clock_out_longitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("clock_out_accuracy_m", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("clock_out_distance_m", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("clock_out_verified", sa.Boolean(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("present", "absent", "half-day", name="attendancestatus"),
            nullable=False,
        ),
        sa.Column("updated_by", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            mysql.TIMESTAMP(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            mysql.TIMESTAMP(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "clock_in_accuracy_m >= 0", name=op.f("ck_attendance_clock_in_accuracy")
        ),
        sa.CheckConstraint(
            "clock_in_distance_m >= 0", name=op.f("ck_attendance_clock_in_distance")
        ),
        sa.CheckConstraint(
            "clock_in_latitude BETWEEN -90 AND 90", name=op.f("ck_attendance_clock_in_latitude")
        ),
        sa.CheckConstraint(
            "clock_in_longitude BETWEEN -180 AND 180", name=op.f("ck_attendance_clock_in_longitude")
        ),
        sa.CheckConstraint(
            "clock_out IS NULL OR (clock_in IS NOT NULL AND clock_out >= clock_in)",
            name=op.f("ck_attendance_clock_order"),
        ),
        sa.CheckConstraint(
            "clock_out_accuracy_m >= 0", name=op.f("ck_attendance_clock_out_accuracy")
        ),
        sa.CheckConstraint(
            "clock_out_distance_m >= 0", name=op.f("ck_attendance_clock_out_distance")
        ),
        sa.CheckConstraint(
            "clock_out_latitude BETWEEN -90 AND 90", name=op.f("ck_attendance_clock_out_latitude")
        ),
        sa.CheckConstraint(
            "clock_out_longitude BETWEEN -180 AND 180",
            name=op.f("ck_attendance_clock_out_longitude"),
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"], name=op.f("fk_attendance_employee_id_employees")
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["employees.id"], name=op.f("fk_attendance_updated_by_employees")
        ),
        sa.ForeignKeyConstraint(
            ["work_location_id"],
            ["work_locations.id"],
            name=op.f("fk_attendance_work_location_id_work_locations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attendance")),
        sa.UniqueConstraint(
            "employee_id", "attendance_date", name=op.f("uq_attendance_employee_id")
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_index(
        "ix_attendance_attendance_date", "attendance", ["attendance_date"], unique=False
    )
    op.create_table(
        "audit_logs",
        sa.Column("actor_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("entity", sa.String(length=50), nullable=False),
        sa.Column("entity_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("before_json", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("after_json", sa.JSON(none_as_null=True), nullable=True),
        sa.Column(
            "created_at",
            mysql.TIMESTAMP(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["employees.id"], name=op.f("fk_audit_logs_actor_id_employees")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "leave_requests",
        sa.Column("employee_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("leave_type_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("leave_reason_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("reason_text", sa.String(length=500), nullable=True),
        sa.Column(
            "duration_type", sa.Enum("half_day", "full_days", name="leaveduration"), nullable=False
        ),
        sa.Column(
            "half_day_period", sa.Enum("morning", "afternoon", name="halfdayperiod"), nullable=True
        ),
        sa.Column("num_days", sa.Numeric(precision=4, scale=1), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("reporting_manager_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("remark", sa.String(length=500), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "approved", "rejected", "cancelled", name="leavestatus"),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("decided_by", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("decided_at", mysql.TIMESTAMP(fsp=6), nullable=True),
        sa.Column("decision_note", sa.String(length=500), nullable=True),
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            mysql.TIMESTAMP(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            mysql.TIMESTAMP(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(duration_type = 'half_day' AND num_days = 0.5 AND half_day_period IS NOT NULL "
            "AND end_date = start_date) OR (duration_type = 'full_days' AND num_days >= 1 "
            "AND num_days = FLOOR(num_days) AND half_day_period IS NULL)",
            name=op.f("ck_leave_requests_valid_duration"),
        ),
        sa.CheckConstraint(
            "decided_by IS NULL OR decided_by <> employee_id",
            name=op.f("ck_leave_requests_no_self_decision"),
        ),
        sa.CheckConstraint("end_date >= start_date", name=op.f("ck_leave_requests_date_order")),
        sa.CheckConstraint(
            "reporting_manager_id <> employee_id",
            name=op.f("ck_leave_requests_manager_not_requester"),
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"], ["employees.id"], name=op.f("fk_leave_requests_decided_by_employees")
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"], name=op.f("fk_leave_requests_employee_id_employees")
        ),
        sa.ForeignKeyConstraint(
            ["leave_reason_id"],
            ["leave_reasons.id"],
            name=op.f("fk_leave_requests_leave_reason_id_leave_reasons"),
        ),
        sa.ForeignKeyConstraint(
            ["leave_type_id"],
            ["leave_types.id"],
            name=op.f("fk_leave_requests_leave_type_id_leave_types"),
        ),
        sa.ForeignKeyConstraint(
            ["reporting_manager_id"],
            ["employees.id"],
            name=op.f("fk_leave_requests_reporting_manager_id_employees"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_leave_requests")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_index(
        "ix_leave_requests_employee_start",
        "leave_requests",
        ["employee_id", "start_date"],
        unique=False,
    )
    op.create_index(
        "ix_leave_requests_manager_status",
        "leave_requests",
        ["reporting_manager_id", "status"],
        unique=False,
    )
    op.create_index("ix_leave_requests_status", "leave_requests", ["status"], unique=False)
    op.create_table(
        "team_managers",
        sa.Column("team_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("employee_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column(
            "assigned_at",
            mysql.TIMESTAMP(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.Column("removed_at", mysql.TIMESTAMP(fsp=6), nullable=True),
        sa.CheckConstraint(
            "removed_at IS NULL OR removed_at >= assigned_at",
            name=op.f("ck_team_managers_manager_dates"),
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"], name=op.f("fk_team_managers_employee_id_employees")
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name=op.f("fk_team_managers_team_id_teams")
        ),
        sa.PrimaryKeyConstraint(
            "team_id", "employee_id", "assigned_at", name=op.f("pk_team_managers")
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_index(
        "ix_team_managers_employee_active",
        "team_managers",
        ["employee_id", "removed_at", "team_id"],
        unique=False,
    )
    op.create_index(
        "ix_team_managers_team_active", "team_managers", ["team_id", "removed_at"], unique=False
    )
    op.create_table(
        "team_members",
        sa.Column("team_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("employee_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column(
            "joined_at",
            mysql.TIMESTAMP(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.Column("left_at", mysql.TIMESTAMP(fsp=6), nullable=True),
        sa.CheckConstraint(
            "left_at IS NULL OR left_at >= joined_at", name=op.f("ck_team_members_membership_dates")
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"], name=op.f("fk_team_members_employee_id_employees")
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name=op.f("fk_team_members_team_id_teams")
        ),
        sa.PrimaryKeyConstraint(
            "team_id", "employee_id", "joined_at", name=op.f("pk_team_members")
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_index(
        "ix_team_members_employee_active", "team_members", ["employee_id", "left_at"], unique=False
    )


def downgrade() -> None:
    # DROP TABLE removes its indexes too. Dropping FK support indexes first is invalid in MySQL.
    op.drop_table("team_members")
    op.drop_table("team_managers")
    op.drop_table("leave_requests")
    op.drop_table("audit_logs")
    op.drop_table("attendance")
    op.drop_table("team_work_locations")
    op.drop_table("role_permissions")
    op.drop_table("employees")
    op.drop_table("work_locations")
    op.drop_table("teams")
    op.drop_table("roles")
    op.drop_table("permissions")
    op.drop_table("leave_types")
    op.drop_table("leave_reasons")
    op.drop_table("id_sequences")

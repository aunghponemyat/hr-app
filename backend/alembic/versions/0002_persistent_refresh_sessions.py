"""persistent refresh sessions

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Generated from the refresh-session model and reviewed for MySQL.
    op.create_table(
        "refresh_sessions",
        sa.Column("employee_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", mysql.TIMESTAMP(fsp=6), nullable=False),
        sa.Column("revoked_at", mysql.TIMESTAMP(fsp=6), nullable=True),
        sa.Column(
            "created_at",
            mysql.TIMESTAMP(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            nullable=False,
        ),
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name=op.f("fk_refresh_sessions_employee_id_employees"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_refresh_sessions_token_hash")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_index(
        "ix_refresh_sessions_employee_id", "refresh_sessions", ["employee_id"], unique=False
    )
    op.create_index(
        "ix_refresh_sessions_expires_at", "refresh_sessions", ["expires_at"], unique=False
    )


def downgrade() -> None:
    # MySQL removes indexes with the table; FK support indexes cannot be dropped first.
    op.drop_table("refresh_sessions")

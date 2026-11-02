"""increase work location radius max to 300

Revision ID: b5f59ae6ab43
Revises: 0002
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'b5f59ae6ab43'
down_revision: str | Sequence[str] | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE work_locations
            DROP CHECK `ck_work_locations_radius_range`,
            ADD CONSTRAINT `ck_work_locations_radius_50_300`
                CHECK (allowed_radius_m BETWEEN 50 AND 300)
    """)


def downgrade() -> None:
    oversized = op.get_bind().scalar(
        sa.text("""
            SELECT COUNT(*)
            FROM work_locations
            WHERE allowed_radius_m > 100
        """)
    )
    if oversized:
        raise RuntimeError(
            "Cannot downgrade while locations exceed 100 metres. "
            "Review those locations before retrying."
        )

    op.execute("""
        ALTER TABLE work_locations
            DROP CHECK `ck_work_locations_radius_50_300`,
            ADD CONSTRAINT `ck_work_locations_radius_range`
                CHECK (allowed_radius_m BETWEEN 50 AND 100)
    """)

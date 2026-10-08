from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Integer, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TABLE_OPTIONS, Base, IdMixin

if TYPE_CHECKING:
    from app.models.team import Team


class WorkLocation(IdMixin, Base):
    __tablename__ = "work_locations"
    __table_args__ = (
        CheckConstraint("latitude BETWEEN -90 AND 90", name="latitude_range"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="longitude_range"),
        CheckConstraint("allowed_radius_m BETWEEN 50 AND 100", name="radius_range"),
        TABLE_OPTIONS,
    )

    name: Mapped[str] = mapped_column(String(100))
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    allowed_radius_m: Mapped[int] = mapped_column(Integer, server_default=text("100"))
    teams: Mapped[list[Team]] = relationship(
        secondary="team_work_locations", back_populates="work_locations"
    )

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TABLE_OPTIONS, Base, IdMixin, UTCDateTime

if TYPE_CHECKING:
    from app.models.employee import Employee
    from app.models.location import WorkLocation


class Team(IdMixin, Base):
    __tablename__ = "teams"

    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    members: Mapped[list[Employee]] = relationship(back_populates="team")
    membership_history: Mapped[list[TeamMember]] = relationship(back_populates="team")
    manager_history: Mapped[list[TeamManager]] = relationship(back_populates="team")
    work_locations: Mapped[list[WorkLocation]] = relationship(
        secondary="team_work_locations", back_populates="teams"
    )


class TeamMember(Base):
    __tablename__ = "team_members"
    __table_args__ = (
        CheckConstraint("left_at IS NULL OR left_at >= joined_at", name="membership_dates"),
        Index("ix_team_members_employee_active", "employee_id", "left_at"),
        TABLE_OPTIONS,
    )

    team_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("teams.id"), primary_key=True
    )
    employee_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("employees.id"), primary_key=True
    )
    joined_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), primary_key=True, server_default=text("CURRENT_TIMESTAMP(6)")
    )
    left_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    team: Mapped[Team] = relationship(back_populates="membership_history")
    employee: Mapped[Employee] = relationship()


class TeamManager(Base):
    __tablename__ = "team_managers"
    __table_args__ = (
        CheckConstraint("removed_at IS NULL OR removed_at >= assigned_at", name="manager_dates"),
        Index("ix_team_managers_employee_active", "employee_id", "removed_at", "team_id"),
        Index("ix_team_managers_team_active", "team_id", "removed_at"),
        TABLE_OPTIONS,
    )

    team_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("teams.id"), primary_key=True
    )
    employee_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("employees.id"), primary_key=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), primary_key=True, server_default=text("CURRENT_TIMESTAMP(6)")
    )
    removed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    team: Mapped[Team] = relationship(back_populates="manager_history")
    employee: Mapped[Employee] = relationship()


class TeamWorkLocation(Base):
    __tablename__ = "team_work_locations"

    team_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("teams.id"), primary_key=True
    )
    work_location_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("work_locations.id"), primary_key=True
    )

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, text
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TABLE_OPTIONS, Base, IdMixin, TimestampMixin, UTCDateTime

if TYPE_CHECKING:
    from app.models.authorization import Role
    from app.models.team import Team


class Employee(IdMixin, TimestampMixin, Base):
    __tablename__ = "employees"
    __table_args__ = (
        CheckConstraint("failed_login_count >= 0", name="nonnegative_failed_logins"),
        TABLE_OPTIONS,
    )

    employee_id: Mapped[str] = mapped_column(String(20), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), ForeignKey("roles.id"))
    team_id: Mapped[int | None] = mapped_column(BIGINT(unsigned=True), ForeignKey("teams.id"))
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    display_name: Mapped[str | None] = mapped_column(String(100))
    position: Mapped[str | None] = mapped_column(String(100))
    department: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("1"))
    must_change_password: Mapped[bool] = mapped_column(Boolean, server_default=text("1"))
    password_changed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    failed_login_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    role: Mapped[Role] = relationship(back_populates="employees")
    team: Mapped[Team | None] = relationship(back_populates="members")

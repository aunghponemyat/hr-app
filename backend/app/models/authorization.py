from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TABLE_OPTIONS, Base, IdMixin

if TYPE_CHECKING:
    from app.models.employee import Employee


class Role(IdMixin, Base):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(50), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    permissions: Mapped[list[Permission]] = relationship(
        secondary="role_permissions", back_populates="roles", passive_deletes=True
    )
    employees: Mapped[list[Employee]] = relationship(back_populates="role")


class Permission(IdMixin, Base):
    __tablename__ = "permissions"
    __table_args__ = (
        CheckConstraint("scope IN ('self', 'team', 'any')", name="valid_scope"),
        TABLE_OPTIONS,
    )

    code: Mapped[str] = mapped_column(String(100), unique=True)
    resource: Mapped[str] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(50))
    scope: Mapped[str] = mapped_column(String(20))
    description: Mapped[str | None] = mapped_column(Text)
    roles: Mapped[list[Role]] = relationship(
        secondary="role_permissions", back_populates="permissions", passive_deletes=True
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )

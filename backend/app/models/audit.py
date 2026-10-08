from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import JsonValue
from sqlalchemy import JSON, ForeignKey, String, text
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, UTCDateTime

if TYPE_CHECKING:
    from app.models.employee import Employee


class AuditLog(IdMixin, Base):
    __tablename__ = "audit_logs"

    actor_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), ForeignKey("employees.id"))
    action: Mapped[str] = mapped_column(String(50))
    entity: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[int] = mapped_column(BIGINT(unsigned=True))
    before_json: Mapped[dict[str, JsonValue] | None] = mapped_column(JSON(none_as_null=True))
    after_json: Mapped[dict[str, JsonValue] | None] = mapped_column(JSON(none_as_null=True))
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=text("CURRENT_TIMESTAMP(6)")
    )
    actor: Mapped[Employee] = relationship()

from sqlalchemy import CheckConstraint, String
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TABLE_OPTIONS, Base


class IdSequence(Base):
    __tablename__ = "id_sequences"
    __table_args__ = (
        CheckConstraint("next_value >= 1", name="positive_next_value"),
        TABLE_OPTIONS,
    )

    name: Mapped[str] = mapped_column(String(50), primary_key=True)
    next_value: Mapped[int] = mapped_column(BIGINT(unsigned=True))

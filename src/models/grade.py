from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Grade(Base):
    __tablename__ = "grades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id", ondelete="CASCADE"))
    graded_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    hit_t1: Mapped[bool | None] = mapped_column(nullable=True)
    hit_t2: Mapped[bool | None] = mapped_column(nullable=True)
    mfe_stock_pct: Mapped[float | None] = mapped_column(nullable=True)
    mae_stock_pct: Mapped[float | None] = mapped_column(nullable=True)
    time_to_t1_min: Mapped[int | None] = mapped_column(nullable=True)
    time_to_t2_min: Mapped[int | None] = mapped_column(nullable=True)
    max_option_gain_pct: Mapped[float | None] = mapped_column(nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    alert = relationship("Alert", back_populates="grades")

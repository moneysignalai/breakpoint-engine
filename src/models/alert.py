from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    symbol: Mapped[str] = mapped_column(String(16))
    direction: Mapped[str] = mapped_column(String(8))
    confidence: Mapped[float]
    expected_window: Mapped[str] = mapped_column(String(16))

    entry: Mapped[float]
    stop: Mapped[float]
    t1: Mapped[float]
    t2: Mapped[float]

    box_high: Mapped[float]
    box_low: Mapped[float]
    range_pct: Mapped[float]
    atr_ratio: Mapped[float]
    vol_ratio: Mapped[float]
    break_vol_mult: Mapped[float]
    extension_pct: Mapped[float]

    market_bias: Mapped[str | None] = mapped_column(String(16), nullable=True)
    vwap_ok: Mapped[bool] = mapped_column(Boolean, default=False)

    alert_text_short: Mapped[str] = mapped_column(Text)
    alert_text_medium: Mapped[str] = mapped_column(Text)
    alert_text_deep: Mapped[str] = mapped_column(Text)

    telegram_status_code: Mapped[int | None]
    telegram_response: Mapped[str | None] = mapped_column(Text, nullable=True)

    option_candidates = relationship("OptionCandidate", back_populates="alert", cascade="all, delete-orphan")
    grades = relationship("Grade", back_populates="alert", cascade="all, delete-orphan")

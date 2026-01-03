from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class OptionCandidate(Base):
    __tablename__ = "option_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id", ondelete="CASCADE"))
    tier: Mapped[str] = mapped_column(String(32))
    contract_symbol: Mapped[str] = mapped_column(String(64))
    expiry: Mapped[str] = mapped_column(String(16))
    strike: Mapped[float]
    call_put: Mapped[str] = mapped_column(String(4))

    bid: Mapped[float]
    ask: Mapped[float]
    mid: Mapped[float]
    spread_pct: Mapped[float]
    volume: Mapped[int]
    oi: Mapped[int]

    delta: Mapped[float | None] = mapped_column(nullable=True)
    gamma: Mapped[float | None] = mapped_column(nullable=True)
    theta: Mapped[float | None] = mapped_column(nullable=True)
    iv: Mapped[float | None] = mapped_column(nullable=True)
    iv_percentile: Mapped[float | None] = mapped_column(nullable=True)

    rationale: Mapped[str] = mapped_column(Text)
    exit_plan: Mapped[str] = mapped_column(Text)

    alert = relationship("Alert", back_populates="option_candidates")

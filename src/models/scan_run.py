from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ScanRun(Base):
    __tablename__ = "scan_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime]
    finished_at: Mapped[datetime | None]
    universe: Mapped[str] = mapped_column(Text)
    symbols_scanned: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    errors_count: Mapped[int] = mapped_column(Integer, default=0)

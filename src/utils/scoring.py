from __future__ import annotations

from src.utils.math import clamp


def cap_score(score: float) -> float:
    return clamp(score, 0.0, 10.0)

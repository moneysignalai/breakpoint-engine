from __future__ import annotations

from loguru import logger

from src.utils.math import clamp


def cap_score(score: float) -> float:
    capped = clamp(score, 0.0, 10.0)
    if capped != score:
        logger.debug("score capped", score=score, capped=capped)
    return capped

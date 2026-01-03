from __future__ import annotations


def pct(a: float, b: float) -> float:
    if b == 0:
        return 0.0
    return (a - b) / b


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def mid_price(bid: float, ask: float) -> float:
    return round((bid + ask) / 2, 4)

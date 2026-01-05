import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import get_settings
from src.strategies.flagship import FlagshipStrategy


def build_bars(start: datetime, count: int, base: float, rng: float = 0.2, vol: int = 100000):
    bars = []
    for i in range(count):
        price = base + rng * (i % 3) / 100
        bars.append({
            "ts": (start + timedelta(minutes=5 * i)).isoformat(),
            "open": price,
            "high": price * 1.001,
            "low": price * 0.999,
            "close": price,
            "volume": vol,
        })
    return bars


def test_flagship_breakout_long():
    strat = FlagshipStrategy()
    start = datetime(2024, 1, 1, 12, 30)
    bars = build_bars(start, 36, 100, rng=0.05, vol=100000)
    for i in range(10):
        bars[i]['high'] = 101
        bars[i]['low'] = 99
    # tighten last box
    for i in range(-12, 0):
        bars[i]['high'] = 100.2
        bars[i]['low'] = 100.0
        bars[i]['close'] = 100.15
    for i in range(-24, -12):
        bars[i]['volume'] = 150000
    # breakout candle
    bars[-1]['close'] = 100.7
    bars[-1]['high'] = 100.8
    bars[-1]['volume'] = 200000

    market = build_bars(start, 36, 400, rng=0.0, vol=150000)
    daily = {"avg_daily_volume": 10_000_000}

    idea, debug = strat.evaluate("TEST", bars, daily, market)
    assert idea is not None
    assert idea.direction == 'LONG'
    assert idea.entry > 0
    assert idea.t2 > idea.t1


def test_flagship_handles_missing_snapshot():
    strat = FlagshipStrategy()
    start = datetime(2024, 1, 1, 12, 30)
    bars = build_bars(start, 36, 100, rng=0.05, vol=100000)
    market = build_bars(start, 36, 400, rng=0.0, vol=150000)

    idea, debug = strat.evaluate("TEST", bars, None, market)

    assert idea is None
    assert "avg_volume_below_min" in debug.get("skip_reasons", [])


def test_flagship_window_override_allows(monkeypatch: pytest.MonkeyPatch):
    strat = FlagshipStrategy()
    settings = get_settings()
    monkeypatch.setattr(settings, "SCAN_OUTSIDE_WINDOW", True)
    monkeypatch.setattr(settings, "ALLOWED_WINDOWS", "00:00-00:10")
    start = datetime(2024, 1, 1, 23, 0)
    bars = build_bars(start, 36, 100, rng=0.05, vol=100000)
    for i in range(10):
        bars[i]['high'] = 101
        bars[i]['low'] = 99
    for i in range(-12, 0):
        bars[i]['high'] = 100.2
        bars[i]['low'] = 100.0
        bars[i]['close'] = 100.15
    for i in range(-24, -12):
        bars[i]['volume'] = 150000
    bars[-1]['close'] = 100.7
    bars[-1]['high'] = 100.8
    bars[-1]['volume'] = 200000
    market = build_bars(start, 36, 400, rng=0.0, vol=150000)
    daily = {"avg_daily_volume": 10_000_000}

    idea, debug = strat.evaluate("TEST", bars, daily, market)

    assert idea is not None
    assert "outside_allowed_window" not in debug.get("skip_reasons", [])


def test_flagship_returns_skip_reasons():
    strat = FlagshipStrategy()
    idea, debug = strat.evaluate("TEST", [], None, [])

    assert idea is None
    assert "insufficient_bars" in debug.get("skip_reasons", [])

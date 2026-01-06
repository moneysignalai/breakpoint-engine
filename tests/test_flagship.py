from datetime import datetime, timedelta
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import get_settings
from src.strategies.flagship import FlagshipStrategy, _to_bars


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

    idea, trace = strat.evaluate("TEST", bars, daily, market)
    assert idea is not None
    assert idea.direction == 'LONG'
    assert idea.entry > 0
    assert idea.t2 > idea.t1
    assert trace.skip_reason is None
    assert trace.computed.get("box_high") is not None
    assert trace.computed.get("vol_ratio") is not None
    assert any(gate.name == "window_gate" for gate in trace.gates)


def test_flagship_handles_missing_snapshot():
    strat = FlagshipStrategy()
    start = datetime(2024, 1, 1, 12, 30)
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

    idea, trace = strat.evaluate("TEST", bars, None, market)

    assert trace.skip_reason != "missing_daily_snapshot"
    assert idea is not None


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

    idea, trace = strat.evaluate("TEST", bars, daily, market)

    assert idea is not None
    assert trace.skip_reason is None


def test_flagship_returns_skip_reasons():
    strat = FlagshipStrategy()
    idea, trace = strat.evaluate("TEST", [], None, [])

    assert idea is None
    assert trace.skip_reason == "insufficient_bars"


def test_to_bars_supports_polygon_and_massive_schemas():
    polygon_bar = {
        "o": 1,
        "h": 2,
        "l": 0.5,
        "c": 1.5,
        "v": 1000,
        "t": 1_700_000_000_000,
    }
    massive_bar = {
        "open": 1,
        "high": 2,
        "low": 0.5,
        "close": 1.5,
        "volume": 1000,
        "ts": "2026-01-05T15:30:00Z",
    }

    bars = _to_bars([polygon_bar, massive_bar], symbol="TEST")

    assert len(bars) == 2
    assert bars[0].open == pytest.approx(1)
    assert bars[1].close == pytest.approx(1.5)

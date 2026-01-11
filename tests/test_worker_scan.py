from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.services import alerts as alert_service
from src.services.db import init_db
from src.worker import run_scan_once


def build_bars(start: datetime, count: int, base: float, rng: float = 0.2, vol: int = 100000):
    bars = []
    for i in range(count):
        price = base + rng * (i % 3) / 100
        bars.append(
            {
                "ts": (start + timedelta(minutes=5 * i)).isoformat(),
                "open": price,
                "high": price * 1.001,
                "low": price * 0.999,
                "close": price,
                "volume": vol,
            }
        )
    return bars


class FakeMassiveClient:
    def __init__(self, bars, market_bars, daily, chain):
        self._bars = bars
        self._market_bars = market_bars
        self._daily = daily
        self._chain = chain

    def get_bars(self, symbol: str, timeframe: str, limit: int):
        if symbol == "QQQ":
            return self._market_bars[-limit:]
        return self._bars[-limit:]

    def get_daily_snapshot(self, symbol: str):
        return self._daily

    def get_option_expirations(self, symbol: str):
        return ["2024-02-16"]

    def get_option_chain(self, symbol: str, expiration: str):
        return self._chain


def test_run_scan_once_triggers_alert(monkeypatch: pytest.MonkeyPatch):
    init_db()
    start = datetime(2024, 1, 1, 12, 30)
    bars = build_bars(start, 36, 100, rng=0.05, vol=120000)
    for i in range(10):
        bars[i]["high"] = 101
        bars[i]["low"] = 99
    for i in range(-12, 0):
        bars[i]["high"] = 100.2
        bars[i]["low"] = 100.0
        bars[i]["close"] = 100.15
        bars[i]["volume"] = 80000
    for i in range(-24, -12):
        bars[i]["volume"] = 150000
    bars[-1]["close"] = 100.7
    bars[-1]["high"] = 100.8
    bars[-1]["volume"] = 220000

    market = build_bars(start, 36, 400, rng=0.0, vol=150000)
    daily = {"avg_daily_volume": 10_000_000, "iv_percentile": 0.4}
    chain = [
        {
            "symbol": "TEST240216C00100000",
            "strike": 100,
            "type": "C",
            "bid": 2.0,
            "ask": 2.2,
            "volume": 500,
            "oi": 1000,
            "delta": 0.5,
            "gamma": 0.1,
            "theta": -0.02,
        }
    ]
    client = FakeMassiveClient(bars, market, daily, chain)

    monkeypatch.setattr("src.worker.settings.UNIVERSE", "TEST")
    monkeypatch.setattr("src.worker.settings.SCAN_OUTSIDE_WINDOW", True)
    monkeypatch.setattr("src.worker.settings.DEBUG_MODE", False)
    monkeypatch.setattr("src.worker.settings.DEBUG_LENIENT_MODE", True)
    monkeypatch.setattr("src.worker.settings.DEBUG_MAX_ALERTS_PER_SCAN", 3)
    monkeypatch.setattr(alert_service, "send_telegram_message", lambda _: (200, "ok"))

    result = run_scan_once(client)

    assert result["alerts"]

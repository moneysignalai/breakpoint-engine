from __future__ import annotations

from datetime import datetime, timedelta, timezone

from loguru import logger

from src.config import get_settings
from src.strategies.flagship import Bar
from src.worker import run_scan_once, settings as worker_settings


class FakeMassiveClient:
    def __init__(self, bars_by_symbol: dict[str, list[Bar]], daily_by_symbol: dict[str, dict]):
        self.bars_by_symbol = bars_by_symbol
        self.daily_by_symbol = daily_by_symbol
        self.base_url = "mock://massive"
        self.provider = "mock"

    def get_bars(self, symbol: str, timeframe: str, limit: int, **_: object) -> list[Bar]:
        bars = self.bars_by_symbol.get(symbol.upper(), [])
        return bars[-limit:]

    def get_daily_snapshot(self, symbol: str) -> dict:
        return self.daily_by_symbol.get(symbol.upper(), {})

    def get_option_expirations(self, symbol: str) -> list[str]:
        base = datetime.now(timezone.utc).date()
        return [(base + timedelta(days=5)).isoformat()]

    def get_option_chain(self, symbol: str, expiration: str) -> list[dict]:
        strike = 100.0
        return [
            {
                "contract_symbol": f"{symbol}C{expiration.replace('-', '')}100",
                "strike": strike,
                "type": "C",
                "bid": 1.5,
                "ask": 1.7,
                "volume": 2000,
                "oi": 6000,
                "delta": 0.45,
            }
        ]


def build_breakout_bars(
    base_price: float,
    *,
    box_range: float,
    total_bars: int,
    box_bars: int,
    breakout_up: bool = True,
    prior_volume: float = 1200,
    box_volume: float = 600,
    breakout_volume: float = 2500,
    high_atr: bool = False,
) -> list[Bar]:
    bars: list[Bar] = []
    ts = datetime.now(timezone.utc) - timedelta(minutes=5 * total_bars)
    box_high = base_price + box_range / 2
    box_low = base_price - box_range / 2

    for idx in range(total_bars - 1):
        price = base_price + (0.02 if idx % 2 == 0 else -0.02)
        high = price + (box_range / 2)
        low = price - (box_range / 2)
        volume = prior_volume if idx < box_bars else box_volume
        bars.append(
            Bar(
                ts=ts,
                open=price,
                high=high,
                low=low,
                close=price,
                volume=volume,
            )
        )
        ts += timedelta(minutes=5)

    if breakout_up:
        breakout_close = box_high * 1.003
        breakout_high = breakout_close * (1.08 if high_atr else 1.01)
        breakout_low = box_low * (0.9 if high_atr else 0.995)
    else:
        breakout_close = box_low * 0.997
        breakout_high = box_high * (1.1 if high_atr else 1.005)
        breakout_low = breakout_close * (0.92 if high_atr else 0.99)

    bars.append(
        Bar(
            ts=ts,
            open=box_high,
            high=breakout_high,
            low=breakout_low,
            close=breakout_close,
            volume=breakout_volume,
        )
    )
    return bars


def run_scenarios() -> None:
    settings = get_settings()
    settings.TELEGRAM_ENABLED = False
    settings.DEBUG_MODE = True
    settings.MIN_AVG_DAILY_VOLUME = 1_000
    settings.ATR_COMP_FACTOR = 1.5
    settings.MINUTES_BETWEEN_SAME_TICKER = 0
    settings.MAX_ALERTS_PER_SCAN = 5
    settings.ALLOWED_WINDOWS = "00:00-23:59"
    settings.SCAN_OUTSIDE_WINDOW = False

    total_bars = settings.BOX_BARS * 3
    bars_by_symbol = {
        "LIQUID": build_breakout_bars(100.0, box_range=0.6, total_bars=total_bars, box_bars=settings.BOX_BARS),
        "LOWVOL": build_breakout_bars(50.0, box_range=0.5, total_bars=total_bars, box_bars=settings.BOX_BARS),
        "HIGHATR": build_breakout_bars(
            120.0,
            box_range=0.8,
            total_bars=total_bars,
            box_bars=settings.BOX_BARS,
            high_atr=True,
        ),
        "OUTWINDOW": build_breakout_bars(75.0, box_range=0.5, total_bars=total_bars, box_bars=settings.BOX_BARS),
        "QQQ": build_breakout_bars(400.0, box_range=1.0, total_bars=total_bars, box_bars=settings.BOX_BARS),
    }
    daily_by_symbol = {
        "LIQUID": {"avg_daily_volume": 5_000_000, "volume": 3_000_000, "iv_percentile": 0.55},
        "LOWVOL": {"avg_daily_volume": 100, "volume": 80, "iv_percentile": 0.5},
        "HIGHATR": {"avg_daily_volume": 3_000_000, "volume": 2_000_000, "iv_percentile": 0.6},
        "OUTWINDOW": {"avg_daily_volume": 4_000_000, "volume": 2_500_000, "iv_percentile": 0.4},
        "QQQ": {"avg_daily_volume": 50_000_000, "volume": 30_000_000, "iv_percentile": 0.35},
    }

    fake_client = FakeMassiveClient(bars_by_symbol, daily_by_symbol)

    logger.info("scenario run: inside window (expect LIQUID to pass)")
    worker_settings.UNIVERSE = "LIQUID,LOWVOL,HIGHATR,OUTWINDOW"
    result_inside = run_scan_once(fake_client)
    logger.info("scenario result", result=result_inside)

    logger.info("scenario run: outside window (expect outside_allowed_window skips)")
    settings.ALLOWED_WINDOWS = "00:00-00:01"
    settings.SCAN_OUTSIDE_WINDOW = True
    result_outside = run_scan_once(fake_client)
    logger.info("scenario result", result=result_outside)


if __name__ == "__main__":
    run_scenarios()

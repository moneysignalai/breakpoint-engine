from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Any, Dict, List, Tuple
from zoneinfo import ZoneInfo

from src.config import get_settings
from src.utils.scoring import cap_score

settings = get_settings()


@dataclass
class Bar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class StockIdea:
    symbol: str
    direction: str
    entry: float
    stop: float
    t1: float
    t2: float
    expected_window: str
    confidence: float
    debug: Dict[str, Any]


def _to_bars(raw: List[Dict[str, Any]]) -> List[Bar]:
    bars: List[Bar] = []
    for b in raw:
        ts = b.get('ts') or b.get('timestamp') or b.get('time')
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        bars.append(Bar(ts=ts, open=float(b['open']), high=float(b['high']), low=float(b['low']), close=float(b['close']), volume=float(b['volume'])))
    return bars


def _atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[float]:
    trs: List[float] = []
    for i in range(1, len(highs)):
        tr = max(highs[i], closes[i - 1]) - min(lows[i], closes[i - 1])
        trs.append(tr)
    atr: List[float] = [0.0]
    for i in range(len(trs)):
        start = max(0, i - period + 1)
        window = trs[start : i + 1]
        atr.append(sum(window) / len(window))
    return atr


def _vwap(bars: List[Bar]) -> float:
    total_vol = sum(b.volume for b in bars)
    if total_vol == 0:
        return bars[-1].close
    weighted = sum(((b.high + b.low + b.close) / 3) * b.volume for b in bars)
    return weighted / total_vol


def _ema(values: List[float], span: int) -> List[float]:
    if not values:
        return []
    alpha = 2 / (span + 1)
    ema = [values[0]]
    for v in values[1:]:
        ema.append(alpha * v + (1 - alpha) * ema[-1])
    return ema


class FlagshipStrategy:
    def __init__(self, tz: str | None = None):
        self.tz = ZoneInfo(tz or settings.TIMEZONE)

    def market_bias(self, market_bars: List[Dict[str, Any]]) -> Tuple[str | None, bool]:
        bars = _to_bars(market_bars)
        closes = [b.close for b in bars]
        vwap_price = _vwap(bars)
        ema_series = _ema(closes, span=20)
        slope = ema_series[-1] - ema_series[-5] if len(ema_series) > 5 else 0
        bias = None
        if closes[-1] > vwap_price and slope > 0:
            bias = 'LONG'
        elif closes[-1] < vwap_price and slope < 0:
            bias = 'SHORT'

        crossings = 0
        for i in range(1, len(closes)):
            above_prev = closes[i - 1] > vwap_price
            above_now = closes[i] > vwap_price
            if above_prev != above_now:
                crossings += 1
        atr_vals = _atr([b.high for b in bars], [b.low for b in bars], closes)
        panic = False
        if len(atr_vals) > 20:
            recent_avg = sum(atr_vals[-20:]) / len(atr_vals[-20:])
            if atr_vals[-1] > 1.5 * recent_avg:
                panic = True
        if crossings >= 3:
            panic = True
        return bias, panic

    def evaluate(self, symbol: str, bars_raw: List[Dict[str, Any]], daily: Dict[str, Any] | None, market_bars: List[Dict[str, Any]]) -> StockIdea | None:
        if len(bars_raw) < settings.BOX_BARS * 3:
            return None
        daily = daily or {}
        bars = _to_bars(bars_raw)
        closes = [b.close for b in bars]
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]

        last_close = closes[-1]
        avg_vol = daily.get('avg_daily_volume') or daily.get('volume') or 0
        if last_close < settings.MIN_PRICE or last_close > settings.MAX_PRICE:
            return None
        if avg_vol < settings.MIN_AVG_DAILY_VOLUME:
            return None

        now = bars[-1].ts
        if now.tzinfo is None:
            now = now.replace(tzinfo=self.tz)
        now = now.astimezone(self.tz)
        from src.services.market_time import parse_windows  # local import

        windows = parse_windows(settings.ALLOWED_WINDOWS)
        if not any(start <= now.time() <= end for start, end in windows):
            return None

        market_bias, panic = self.market_bias(market_bars)
        if panic:
            return None

        breakout_bar = bars[-1]
        box = bars[-settings.BOX_BARS - 1 : -1]
        prior_box = bars[-2 * settings.BOX_BARS - 1 : -settings.BOX_BARS - 1]
        box_high = max(b.high for b in box)
        box_low = min(b.low for b in box)
        range_pct = (box_high - box_low) / last_close
        if range_pct > settings.BOX_MAX_RANGE_PCT:
            return None

        atr_series = _atr(highs, lows, closes)
        if len(atr_series) < 15:
            return None
        atr_current = atr_series[-1]
        atr_mean_50 = sum(atr_series[-50:]) / len(atr_series[-50:]) if len(atr_series) >= 50 else sum(atr_series) / len(atr_series)
        atr_ratio = atr_current / atr_mean_50 if atr_mean_50 else 0
        if atr_ratio > settings.ATR_COMP_FACTOR:
            return None

        avg_vol_box = sum(b.volume for b in box) / len(box)
        avg_vol_prior = sum(b.volume for b in prior_box) / len(prior_box) if prior_box else avg_vol_box
        vol_ratio = avg_vol_box / avg_vol_prior if avg_vol_prior else 1
        if vol_ratio > settings.VOL_CONTRACTION_FACTOR:
            return None

        closes_outside = [b for b in box if b.close > box_high or b.close < box_low]
        if len(closes_outside) > 2:
            return None

        break_vol_mult = breakout_bar.volume / avg_vol_box if avg_vol_box else 0
        vwap_price = _vwap(bars)
        extension_pct = (last_close - box_high) / box_high if last_close >= box_high else (box_low - last_close) / box_low

        direction = None
        if last_close >= box_high * (1 + settings.BREAK_BUFFER_PCT) and break_vol_mult >= settings.BREAK_VOL_MULT and last_close <= box_high * (1 + settings.MAX_EXTENSION_PCT):
            if not settings.VWAP_CONFIRM or last_close > vwap_price:
                direction = 'LONG'
        if last_close <= box_low * (1 - settings.BREAK_BUFFER_PCT) and break_vol_mult >= settings.BREAK_VOL_MULT and last_close >= box_low * (1 - settings.MAX_EXTENSION_PCT):
            if not settings.VWAP_CONFIRM or last_close < vwap_price:
                direction = 'SHORT'

        if not direction:
            return None

        vwap_ok = (last_close > vwap_price) if direction == 'LONG' else (last_close < vwap_price)
        entry = box_high * (1 + settings.ENTRY_BUFFER_PCT) if direction == 'LONG' else box_low * (1 - settings.ENTRY_BUFFER_PCT)
        stop_candidate = box_high * (1 - settings.STOP_BUFFER_PCT) if direction == 'LONG' else box_low * (1 + settings.STOP_BUFFER_PCT)
        midpoint = (box_high + box_low) / 2
        stop = min(stop_candidate, midpoint) if direction == 'LONG' else max(stop_candidate, midpoint)
        risk = abs(entry - stop)
        if risk == 0:
            return None
        t1 = entry + risk if direction == 'LONG' else entry - risk
        t2 = entry + 2 * risk if direction == 'LONG' else entry - 2 * risk

        expected_window = "same_day" if now.time() < time(14, 0) else "1_3_days"

        confidence = 7.0
        if market_bias == direction:
            confidence += 0.5
        if break_vol_mult >= 2.0:
            confidence += 0.5
        candle_range = box[-1].high - box[-1].low
        if candle_range > 0:
            pos_in_range = (box[-1].close - box[-1].low) / candle_range
            if direction == 'LONG' and pos_in_range >= 0.8:
                confidence += 0.5
            if direction == 'SHORT' and pos_in_range <= 0.2:
                confidence += 0.5
        confidence = cap_score(confidence)

        debug = {
            "range_pct": range_pct,
            "atr_ratio": atr_ratio,
            "vol_ratio": vol_ratio,
            "break_vol_mult": break_vol_mult,
            "extension_pct": extension_pct,
            "vwap_ok": vwap_ok,
            "market_bias": market_bias,
            "box_high": box_high,
            "box_low": box_low,
            "debug_reasons": [],
        }
        return StockIdea(
            symbol=symbol,
            direction=direction,
            entry=entry,
            stop=stop,
            t1=t1,
            t2=t2,
            expected_window=expected_window,
            confidence=confidence,
            debug=debug,
        )

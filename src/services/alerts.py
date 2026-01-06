from __future__ import annotations

from datetime import datetime, time, timezone
import re
from typing import Any, Dict

import httpx
from loguru import logger
from zoneinfo import ZoneInfo

from src.config import get_settings

settings = get_settings()


def send_telegram_message(text: str) -> tuple[int | None, str]:
    enabled = bool(settings.TELEGRAM_ENABLED)
    logger.info(f"Telegram enabled: {enabled} (TELEGRAM_ENABLED={settings.TELEGRAM_ENABLED})")
    if not enabled:
        return None, "telegram-disabled"
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        return None, "telegram-missing-config"
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": settings.TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        resp = httpx.post(url, json=payload, timeout=10.0)
        return resp.status_code, resp.text
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Telegram send failed: {exc}")
        return None, str(exc)


def _format_price(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "N/A"


def _format_percent(value: Any) -> str:
    try:
        return f"{float(value) * 100:.2f}"
    except (TypeError, ValueError):
        return "N/A"


def _format_delta(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "N/A"


def _normalize_call_put(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, str) and value:
        cp = value.strip().upper()
        if cp in {"C", "CALL"}:
            return "C"
        if cp in {"P", "PUT"}:
            return "P"
    return None


def _parse_strike_and_cp(contract_symbol: str) -> tuple[str | None, str | None]:
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)([CP])$", contract_symbol)
    if not match:
        return None, None
    return match.group(1), match.group(2)


def _format_spread_percent(option: dict[str, Any]) -> str:
    spread_pct = option.get("spread_pct")
    if spread_pct is not None:
        try:
            return f"{float(spread_pct) * 100:.2f}"
        except (TypeError, ValueError):
            return "N/A"

    bid = option.get("bid")
    ask = option.get("ask")
    try:
        if bid is not None and ask is not None:
            bid_f = float(bid)
            ask_f = float(ask)
            if bid_f >= 0 and ask_f >= 0 and (bid_f + ask_f) > 0:
                mid = (bid_f + ask_f) / 2
                if mid > 0:
                    return f"{((ask_f - bid_f) / mid) * 100:.2f}"
    except (TypeError, ValueError):
        return "N/A"
    return "N/A"


def _format_mid(option: dict[str, Any]) -> str:
    mid = option.get("mid")
    try:
        if mid is not None:
            return f"{float(mid):.2f}"
    except (TypeError, ValueError):
        return "N/A"

    bid = option.get("bid")
    ask = option.get("ask")
    try:
        if bid is not None and ask is not None:
            return f"{(float(bid) + float(ask)) / 2:.2f}"
    except (TypeError, ValueError):
        return "N/A"
    return "N/A"


def _format_dte(expiry: Any, alert: Dict[str, Any]) -> str:
    if not expiry:
        return "DTE N/A"
    alert_ts = alert.get("ts") or alert.get("triggered_at")
    trigger_dt: datetime
    try:
        if isinstance(alert_ts, datetime):
            trigger_dt = alert_ts
        elif isinstance(alert_ts, str):
            trigger_dt = datetime.fromisoformat(alert_ts)
        else:
            trigger_dt = datetime.now(timezone.utc)
    except Exception:
        trigger_dt = datetime.now(timezone.utc)

    try:
        if isinstance(expiry, datetime):
            expiry_dt = expiry
        elif isinstance(expiry, str):
            expiry_dt = datetime.fromisoformat(expiry)
        else:
            return "DTE N/A"
        dte = (expiry_dt.date() - trigger_dt.date()).days
        if dte < 0:
            return "DTE N/A"
        return f"{dte} DTE"
    except Exception:
        return "DTE N/A"


def _format_option_line(option: dict[str, Any], alert: Dict[str, Any]) -> tuple[str, str]:
    strike_val = option.get("strike")
    strike_display: str | None = None
    cp_display = _normalize_call_put(option.get("call_put"))

    if strike_val is None or cp_display is None:
        cs = option.get("contract_symbol")
        if cs:
            parsed_strike, parsed_cp = _parse_strike_and_cp(str(cs))
            if strike_val is None:
                strike_val = parsed_strike
            if cp_display is None:
                cp_display = parsed_cp

    try:
        if strike_val is not None and float(strike_val).is_integer():
            strike_display = f"{int(float(strike_val))}"
        elif strike_val is not None:
            strike_display = f"{float(strike_val):.2f}"
    except (TypeError, ValueError):
        strike_display = str(strike_val) if strike_val is not None else None

    if not strike_display:
        strike_display = option.get("contract_symbol", "N/A")

    cp_display = cp_display or "?"
    delta_display = _format_delta(option.get("delta"))
    mid_display = _format_mid(option)
    spread_display_raw = _format_spread_percent(option)
    spread_display = f"{spread_display_raw}%" if spread_display_raw != "N/A" else "N/A"
    dte_display = _format_dte(option.get("expiry"), alert)

    return (
        f"{strike_display}{cp_display}",
        f"({dte_display} | Δ {delta_display} | Mid {mid_display} | Sprd {spread_display})",
    )


def _format_market_bias(value: Any) -> str:
    if value in {"LONG", "Bullish"}:
        return "Bullish"
    if value in {"SHORT", "Bearish"}:
        return "Bearish"
    if value is None:
        return "Unknown"
    return str(value)


def _format_expected_window(value: Any) -> str:
    mapping = {
        "same_day": "Same day → 1–3 days",
        "1_3_days": "1–3 days",
        "5_10_days": "5–10 days",
    }
    return mapping.get(value, "Unknown")


def _format_vwap(value: Any) -> str:
    if value is True:
        return "Confirmed"
    if value is False:
        return "Not confirmed"
    return "Unknown"


def _format_timestamp_et(alert: Dict[str, Any]) -> str:
    dt_et = _get_alert_datetime_et(alert)
    return dt_et.strftime("%m-%d-%Y %I:%M %p ET")


def _get_alert_datetime_et(alert: Dict[str, Any]) -> datetime:
    tz = ZoneInfo(settings.TIMEZONE)
    alert_ts = alert.get("ts") or alert.get("triggered_at") or alert.get("created_at")
    try:
        if isinstance(alert_ts, datetime):
            dt = alert_ts
        elif isinstance(alert_ts, str):
            dt = datetime.fromisoformat(alert_ts)
        else:
            dt = datetime.now(timezone.utc)
    except Exception:
        dt = datetime.now(timezone.utc)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_et = dt.astimezone(tz)
    return dt_et


def _format_session_label(alert: Dict[str, Any]) -> tuple[str, str]:
    dt_et = _get_alert_datetime_et(alert)
    t = dt_et.time()
    rth_start = time(9, 30)
    rth_end = time(16, 0)
    ah_start = time(16, 0)
    ah_end = time(20, 0)
    pmkt_start = time(4, 0)

    if rth_start <= t <= rth_end:
        return "⏱", "RTH"
    if ah_start < t <= ah_end or t > ah_end:
        return "🌙", "AH"
    if pmkt_start <= t < rth_start:
        return "🌅", "PM"
    return "🌅", "PM"


def build_alert_texts(alert: Dict[str, Any], options: list[Dict[str, Any]] | None = None) -> dict[str, str]:
    alert_mode = str(alert.get("alert_mode") or "TRADE").upper()
    alert_label = str(alert.get("alert_label") or "ALERT").upper()
    if alert_mode not in {"TRADE", "WATCHLIST"}:
        alert_mode = "TRADE"
    symbol = alert.get("symbol", "?")
    direction = alert.get("direction", "?")
    entry = alert.get("entry")
    stop = alert.get("stop")
    t1 = alert.get("t1")
    t2 = alert.get("t2")
    confidence = alert.get("confidence")
    box_high = alert.get("box_high")
    box_low = alert.get("box_low")
    break_vol_mult = alert.get("break_vol_mult")
    range_pct = alert.get("range_pct")
    atr_ratio = alert.get("atr_ratio")
    extension_pct = alert.get("extension_pct")
    vwap_ok = alert.get("vwap_ok")
    market_bias = alert.get("market_bias")
    expected_window = alert.get("expected_window")

    short_prefix = ""
    if alert_mode == "WATCHLIST" or alert_label not in {"ALERT", "TRADE"}:
        short_prefix = f"[{alert_label if alert_label else alert_mode}] "
    short = (
        f"{short_prefix}{symbol} {direction} entry {_format_price(entry)} stop {_format_price(stop)} "
        f"T1 {_format_price(t1)} T2 {_format_price(t2)} (conf {float(confidence):.1f})"
        if confidence is not None
        else f"{short_prefix}{symbol} {direction} entry {_format_price(entry)} stop {_format_price(stop)} T1 {_format_price(t1)} T2 {_format_price(t2)}"
    )

    entry_phrase = "hold above" if str(direction).upper() != "SHORT" else "hold below"
    vwap_text = _format_vwap(vwap_ok)
    bias_text = _format_market_bias(market_bias)
    expected_window_text = _format_expected_window(expected_window)
    ts_et = _format_timestamp_et(alert)
    session_emoji, session_label = _format_session_label(alert)
    box_timeframe = "5m"
    vol_text = f"{float(break_vol_mult):.2f}" if isinstance(break_vol_mult, (int, float)) else "N/A"
    direction_norm = str(direction).upper() if direction is not None else None
    if direction_norm == "LONG":
        trend_description = "Uptrend"
    elif direction_norm == "SHORT":
        trend_description = "Downtrend"
    else:
        trend_description = "Range"

    header_label = alert_label if alert_label else "ALERT"
    if alert_mode == "WATCHLIST":
        header_label = "WATCHLIST" if alert_label == "ALERT" else alert_label
    standard_lines = [
        "─────────────────",
        f"⚡ BREAKPOINT {header_label} - {symbol}",
        f"🕒 {ts_et}  ",
        f"⏰ {session_emoji} {session_label} · 🚦 Bias: {bias_text}",
        "",
        "🧠 SETUP",
        (
            f"• Box Range: {_format_percent(range_pct)}% ({settings.BOX_BARS}×{box_timeframe}) "
            f"· Break: {_format_percent(extension_pct)}% · Vol: {vol_text}×"
        ),
        f"• VWAP: {vwap_text} · Trend: {trend_description}",
        "",
        "📈 STOCK PLAN",
        f"• Entry: {_format_price(entry)} ({entry_phrase})",
        f"• Invalidation: {_format_price(stop)} (back inside box)",
        f"• Targets: {_format_price(t1)} → {_format_price(t2)}",
        f"• Window: {expected_window_text}",
        "",
        "🎯 OPTIONS (Weekly / Liquid)",
    ]

    if options:
        tier_map: dict[str, dict[str, Any]] = {}
        for opt in options:
            opt_with_alert = {**opt, "alert": alert}
            tier = str(opt.get("tier", "")).lower()
            tier_map[tier] = opt_with_alert

        tiers = [
            ("Conservative", "🟢"),
            ("Standard", "🟡"),
            ("Aggressive", "🔴"),
        ]
        label_width = max(len(f"{emoji} {name}:") for name, emoji in tiers)
        for tier, emoji in tiers:
            opt = tier_map.get(tier.lower(), {})
            opt.setdefault("tier", tier)
            opt.setdefault("alert", alert)
            strike_cp, details = _format_option_line(opt, alert)
            label = f"{emoji} {tier}:".ljust(label_width + 2)
            standard_lines.append(f"• {label} {strike_cp}")
            standard_lines.append(details)
    else:
        standard_lines.append(
            "• stock-only (no liquid contracts / IV too high / unavailable)"
        )

    standard_lines.extend(
        [
            "",
            f"🧪 Mode: {alert_mode.title()} ({alert_label.title() if alert_label else 'Alert'})",
            "🛡️ RISK NOTES",
            "• Take 40–60% at T1 · Runner to T2",
            "• Time stop: 30–60 min if no continuation",
            "• Hard exit if invalidation triggers",
            "",
            f"⭐ Confidence: {float(confidence):.1f} / 10" if confidence is not None else "⭐ Confidence: N/A",
            "─────────────────",
        ]
    )

    standard = "\n".join(standard_lines)

    deep_lines = [
        f"{symbol} {direction} compression breakout",
        f"Box: {_format_price(box_low)}-{_format_price(box_high)} (range {_format_percent(range_pct)}%)",
        f"Trigger close beyond box: {_format_percent(extension_pct)}% beyond edge",
        f"Breakout volume: {_format_price(break_vol_mult)}x box avg",
        f"ATR compression ratio: {_format_price(atr_ratio)}",
        f"VWAP confirmation: {vwap_ok}",
        f"Market bias: {market_bias}",
        f"Plan: entry {_format_price(entry)} stop {_format_price(stop)} T1 {_format_price(t1)} T2 {_format_price(t2)} (conf {confidence:.1f})" if confidence is not None else f"Plan: entry {_format_price(entry)} stop {_format_price(stop)} T1 {_format_price(t1)} T2 {_format_price(t2)}",
    ]
    if options:
        for opt in options:
            spread_display = _format_spread_percent(opt)
            try:
                spread_display = float(spread_display)
                spread_display_str = f"{spread_display:.1f}"
            except (TypeError, ValueError):
                spread_display_str = "N/A"
            deep_lines.append(
                f"{opt.get('tier')}: {opt.get('contract_symbol')} mid {_format_mid(opt)} sprd {spread_display_str}% vol {opt.get('volume')} oi {opt.get('oi')} delta {opt.get('delta')}"
            )
    deep_lines.append("Exit: Take 40-60% at T1, runner to T2, time stop 30-60m if no continuation, exit on invalidation")
    deep = "\n".join(deep_lines)

    texts = {"short": short, "standard": standard, "deep": deep}
    texts["medium"] = standard
    texts["deep_dive"] = deep
    return texts

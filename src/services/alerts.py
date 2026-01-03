from __future__ import annotations

from typing import Any, Dict

import httpx
from loguru import logger

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


def build_alert_texts(alert: Dict[str, Any], options: list[Dict[str, Any]] | None = None) -> dict[str, str]:
    symbol = alert['symbol']
    direction = alert['direction']
    entry = alert['entry']
    stop = alert['stop']
    t1 = alert['t1']
    t2 = alert['t2']
    confidence = alert['confidence']
    box_high = alert['box_high']
    box_low = alert['box_low']
    break_vol_mult = alert['break_vol_mult']
    range_pct = alert['range_pct']
    atr_ratio = alert['atr_ratio']
    extension_pct = alert['extension_pct']
    vwap_ok = alert['vwap_ok']
    market_bias = alert.get('market_bias')

    short = f"{symbol} {direction} entry {entry:.2f} stop {stop:.2f} T1 {t1:.2f} T2 {t2:.2f} (conf {confidence:.1f})"
    medium = short + f" box[{box_low:.2f}-{box_high:.2f}] volx{break_vol_mult:.2f} range {range_pct*100:.2f}% atr_ratio {atr_ratio:.2f}"

    deep_lines = [
        f"{symbol} {direction} compression breakout",
        f"Box: {box_low:.2f}-{box_high:.2f} (range {range_pct*100:.2f}%)",
        f"Trigger close beyond box: {extension_pct*100:.2f}% beyond edge",
        f"Breakout volume: {break_vol_mult:.2f}x box avg",
        f"ATR compression ratio: {atr_ratio:.2f}",
        f"VWAP confirmation: {vwap_ok}",
        f"Market bias: {market_bias}",
        f"Plan: entry {entry:.2f} stop {stop:.2f} T1 {t1:.2f} T2 {t2:.2f} (conf {confidence:.1f})",
    ]
    if options:
        for opt in options:
            deep_lines.append(
                f"{opt['tier']}: {opt['contract_symbol']} mid {opt['mid']:.2f} sprd {opt['spread_pct']*100:.1f}% vol {opt['volume']} oi {opt['oi']} delta {opt.get('delta')}"
            )
    deep_lines.append("Exit: Take 40-60% at T1, runner to T2, time stop 30-60m if no continuation, exit on invalidation")
    deep = "\n".join(deep_lines)
    return {"short": short, "medium": medium, "deep_dive": deep}

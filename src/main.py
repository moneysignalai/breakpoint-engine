from __future__ import annotations

import os
import platform
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from loguru import logger
from sqlalchemy.orm import joinedload

from src.config import get_settings
from src.models.alert import Alert
from src.services.alerts import build_alert_texts, send_telegram_message
from src.services.db import session_scope, init_db
from src.services.massive_client import MassiveClient
from src.utils import configure_logging
from src.worker import run_scan_once

configure_logging("web")

app = FastAPI(title="Breakout Engine")
settings = get_settings()
DEBUG_ENDPOINTS_ENABLED = os.getenv("DEBUG_ENDPOINTS_ENABLED", "false").lower() == "true"

_debug_sample_alert_lock = threading.Lock()
_last_debug_sample_alert_ts = 0.0

logger.info(
    "web boot",
    settings=settings.non_secret_dict(),
    python_version=platform.python_version(),
)
init_db()


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/config")
def config() -> Dict[str, Any]:
    return settings.non_secret_dict()


@app.get("/debug/settings")
def debug_settings() -> Dict[str, Any]:
    if not DEBUG_ENDPOINTS_ENABLED:
        raise HTTPException(status_code=404)
    return settings.non_secret_dict()


@app.get("/debug/massive/health")
def massive_health(symbol: str = "SPY") -> Dict[str, Any]:
    if not DEBUG_ENDPOINTS_ENABLED:
        raise HTTPException(status_code=404)

    client = MassiveClient()
    upper_symbol = symbol.upper()
    response: Dict[str, Any] = {
        "symbol": upper_symbol,
        "base_url": client.base_url,
        "base_url_source": getattr(client, "base_url_source", "unknown"),
        "provider": client.provider,
        "errors": [],
    }

    bars = []
    try:
        bars = client.get_bars(upper_symbol, timeframe="5m", limit=settings.BOX_BARS * 3)
        response["bars_count"] = len(bars)
        if bars:
            last_ts = bars[-1].get("t") or bars[-1].get("ts")
            response["last_bar_timestamp"] = last_ts
    except Exception as exc:  # noqa: BLE001
        response["errors"].append({"stage": "bars", "error": str(exc)})

    try:
        daily = client.get_daily_snapshot(upper_symbol)
        response["avg_daily_volume"] = daily.get("avg_daily_volume") if isinstance(daily, dict) else None
        response["daily_volume"] = daily.get("volume") if isinstance(daily, dict) else None
    except Exception as exc:  # noqa: BLE001
        response["errors"].append({"stage": "daily_snapshot", "error": str(exc)})
    finally:
        client.close()

    return response


@app.post("/run-scan")
def run_scan_endpoint() -> Dict[str, Any]:
    logger.info("Manual scan triggered via API")
    return run_scan_once()


@app.get("/latest-alerts")
def latest_alerts(limit: int = 20) -> Dict[str, Any]:
    with session_scope() as session:
        alerts = (
            session.query(Alert)
            .options(joinedload(Alert.option_candidates))
            .order_by(Alert.created_at.desc())
            .limit(limit)
            .all()
        )
        data = []
        for a in alerts:
            data.append(
                {
                    "id": a.id,
                    "symbol": a.symbol,
                    "direction": a.direction,
                    "confidence": a.confidence,
                    "entry": a.entry,
                    "stop": a.stop,
                    "t1": a.t1,
                    "t2": a.t2,
                    "created_at": a.created_at.isoformat(),
                    "options": [
                        {
                            "tier": oc.tier,
                            "contract_symbol": oc.contract_symbol,
                            "expiry": oc.expiry,
                            "strike": oc.strike,
                            "call_put": oc.call_put,
                            "bid": oc.bid,
                            "ask": oc.ask,
                            "mid": oc.mid,
                        }
                        for oc in a.option_candidates
                    ],
                }
            )
        return {"alerts": data}


@app.get("/")
def root() -> Dict[str, str]:
    return {"message": "Breakout engine alive"}


@app.get("/debug/test-telegram")
def test_telegram() -> Dict[str, bool]:
    send_telegram_message("✅ Telegram test successful – Breakpoint Engine is live.")
    return {"ok": True}


@app.post("/debug/send-sample-alert")
def send_sample_alert() -> Dict[str, Any]:
    global _last_debug_sample_alert_ts

    if not DEBUG_ENDPOINTS_ENABLED:
        raise HTTPException(status_code=404)

    logger.info("debug sample alert requested")

    with _debug_sample_alert_lock:
        now = time.time()
        elapsed = now - _last_debug_sample_alert_ts
        if elapsed < 30:
            retry_after = int(30 - elapsed)
            logger.info("debug sample alert suppressed (cooldown)")
            return {
                "ok": True,
                "sent": False,
                "reason": "cooldown",
                "retry_after_sec": retry_after,
            }

        _last_debug_sample_alert_ts = now

    sample_alert = {
        "symbol": "SPY",
        "direction": "LONG",
        "entry": 525.25,
        "stop": 519.5,
        "t1": 533.0,
        "t2": 540.0,
        "confidence": 7.8,
        "box_high": 522.0,
        "box_low": 518.0,
        "range_pct": 0.0076,
        "atr_ratio": 1.2,
        "break_vol_mult": 2.4,
        "extension_pct": 0.0035,
        "vwap_ok": True,
        "market_bias": "Bullish",
        "expected_window": "1_3_days",
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    sample_options = [
        {
            "tier": "Conservative",
            "contract_symbol": "SPY240621C520",
            "expiry": datetime.now(timezone.utc).date().isoformat(),
            "strike": 520,
            "call_put": "C",
            "bid": 6.85,
            "ask": 7.05,
            "volume": 1123,
            "oi": 20450,
            "delta": 0.45,
        },
        {
            "tier": "Standard",
            "contract_symbol": "SPY240621C525",
            "expiry": datetime.now(timezone.utc).date().isoformat(),
            "strike": 525,
            "call_put": "C",
            "bid": 4.35,
            "ask": 4.55,
            "volume": 8420,
            "oi": 35670,
            "delta": 0.38,
        },
        {
            "tier": "Aggressive",
            "contract_symbol": "SPY240621C530",
            "expiry": datetime.now(timezone.utc).date().isoformat(),
            "strike": 530,
            "call_put": "C",
            "bid": 2.35,
            "ask": 2.55,
            "volume": 15320,
            "oi": 41200,
            "delta": 0.31,
        },
    ]

    texts = build_alert_texts(sample_alert, sample_options)
    status_code, response = send_telegram_message(texts.get("standard", ""))

    logger.info(
        "debug sample alert sent",
        status_code=status_code,
        response=response,
    )

    return {"ok": True, "sent": True}

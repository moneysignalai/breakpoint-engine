from __future__ import annotations

import os
import platform
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from loguru import logger
from sqlalchemy.orm import joinedload

from src.config import get_settings
from src.models.alert import Alert
from src.services.alerts import send_telegram_message
from src.services.db import session_scope, init_db
from src.utils import configure_logging
from src.worker import run_scan_once

configure_logging("web")

app = FastAPI(title="Breakout Engine")
settings = get_settings()
DEBUG_ENDPOINTS_ENABLED = os.getenv("DEBUG_ENDPOINTS_ENABLED", "false").lower() == "true"

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

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger

from src.config import get_settings
from src.models.alert import Alert
from src.services import alerts as alert_service
from src.services.db import init_db, session_scope


def _build_fake_alert_dict(symbol: str) -> dict:
    return {
        "symbol": symbol,
        "direction": "LONG",
        "confidence": 8.2,
        "alert_mode": "TRADE",
        "alert_label": "TRADE",
        "window_label": "RTH",
        "expected_window": "same_day",
        "entry": 100.25,
        "stop": 99.5,
        "t1": 101.0,
        "t2": 102.0,
        "box_high": 100.1,
        "box_low": 99.2,
        "range_pct": 0.009,
        "atr_ratio": 0.6,
        "vol_ratio": 0.7,
        "break_vol_mult": 1.8,
        "extension_pct": 0.004,
        "market_bias": "LONG",
        "vwap_ok": True,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    settings = get_settings()
    init_db()
    symbol = "TEST"
    alert_dict = _build_fake_alert_dict(symbol)
    texts = alert_service.build_alert_texts(alert_dict, options=None)

    logger.info("test alert pipeline", symbol=symbol, telegram_enabled=settings.TELEGRAM_ENABLED)

    with session_scope() as session:
        alert_row = Alert(
            symbol=symbol,
            direction=alert_dict["direction"],
            confidence=alert_dict["confidence"],
            expected_window=alert_dict["expected_window"],
            entry=alert_dict["entry"],
            stop=alert_dict["stop"],
            t1=alert_dict["t1"],
            t2=alert_dict["t2"],
            box_high=alert_dict["box_high"],
            box_low=alert_dict["box_low"],
            range_pct=alert_dict["range_pct"],
            atr_ratio=alert_dict["atr_ratio"],
            vol_ratio=alert_dict["vol_ratio"],
            break_vol_mult=alert_dict["break_vol_mult"],
            extension_pct=alert_dict["extension_pct"],
            market_bias=alert_dict["market_bias"],
            vwap_ok=alert_dict["vwap_ok"],
            alert_text_short=texts["short"],
            alert_text_medium=texts["medium"],
            alert_text_deep=texts["deep_dive"],
            telegram_status_code=None,
            telegram_response="pipeline-test",
        )
        session.add(alert_row)
        session.flush()
        logger.info("test alert persisted", alert_id=alert_row.id, symbol=symbol)

    status_code, resp = alert_service.send_telegram_message(texts["short"])
    logger.info(
        "test alert telegram send",
        symbol=symbol,
        status_code=status_code,
        response=resp,
    )


if __name__ == "__main__":
    main()

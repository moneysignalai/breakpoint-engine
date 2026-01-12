from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger

from src.config import get_settings
from src.services import alerts as alert_service


def _build_dummy_alert() -> dict:
    return {
        "symbol": "TST",
        "direction": "LONG",
        "confidence": 7.4,
        "alert_mode": "TRADE",
        "alert_label": "TRADE",
        "window_label": "RTH",
        "expected_window": "same_day",
        "entry": 101.2,
        "stop": 99.8,
        "t1": 103.4,
        "t2": 105.0,
        "box_high": 100.8,
        "box_low": 100.1,
        "range_pct": 0.007,
        "atr_ratio": 0.65,
        "vol_ratio": 0.72,
        "break_vol_mult": 1.9,
        "extension_pct": 0.003,
        "market_bias": "LONG",
        "vwap_ok": True,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


def _build_dummy_options() -> list[dict]:
    return [
        {
            "tier": "Conservative",
            "contract_symbol": "TST240621C100",
            "expiry": datetime.now(timezone.utc).date().isoformat(),
            "strike": 100,
            "call_put": "C",
            "bid": 2.15,
            "ask": 2.35,
            "volume": 15400,
            "oi": 43210,
            "delta": 0.48,
            "spread_pct": 0.08,
        },
        {
            "tier": "Standard",
            "contract_symbol": "TST240621C102",
            "expiry": datetime.now(timezone.utc).date().isoformat(),
            "strike": 102,
            "call_put": "C",
            "bid": 1.35,
            "ask": 1.55,
            "volume": 9900,
            "oi": 21000,
            "delta": 0.36,
            "spread_pct": 0.12,
        },
        {
            "tier": "Aggressive",
            "contract_symbol": "TST240621C104",
            "expiry": datetime.now(timezone.utc).date().isoformat(),
            "strike": 104,
            "call_put": "C",
            "bid": 0.75,
            "ask": 0.95,
            "volume": 5200,
            "oi": 12000,
            "delta": 0.27,
            "spread_pct": 0.18,
        },
    ]


def main() -> None:
    settings = get_settings()
    alert_dict = _build_dummy_alert()
    option_payloads = _build_dummy_options()
    texts = alert_service.build_alert_texts(alert_dict, option_payloads)

    logger.info(
        "telegram test payload",
        enabled=settings.TELEGRAM_ENABLED,
        chat_id=settings.TELEGRAM_CHAT_ID,
        alert_symbol=alert_dict["symbol"],
    )

    status_code, resp = alert_service.send_telegram_message(texts["short"])
    logger.info(
        "telegram test payload result",
        status_code=status_code,
        response=resp,
    )


if __name__ == "__main__":
    main()

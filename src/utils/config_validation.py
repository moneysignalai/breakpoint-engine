from __future__ import annotations

from zoneinfo import ZoneInfo

from loguru import logger

from src.config import Settings
from src.services.market_time import parse_windows


def validate_runtime_config(settings: Settings) -> None:
    """Validate configuration and abort early if values are inconsistent."""

    logger.info(
        "config resolved",
        base_url=settings.MASSIVE_API_BASE_URL,
        bars_path_template=settings.MASSIVE_BARS_PATH_TEMPLATE,
        timezone=settings.TIMEZONE,
        scan_window=settings.ALLOWED_WINDOWS,
    )

    if not settings.MASSIVE_API_KEY:
        raise RuntimeError("Missing MASSIVE_API_KEY")

    if settings.TELEGRAM_ENABLED and (not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID):
        logger.warning(
            "Telegram enabled but missing config",
            enabled=settings.TELEGRAM_ENABLED,
            missing_token=not bool(settings.TELEGRAM_BOT_TOKEN),
            missing_chat_id=not bool(settings.TELEGRAM_CHAT_ID),
        )

    if settings.DATA_PROVIDER.lower() == "massive" and "polygon.io" in settings.MASSIVE_API_BASE_URL:
        logger.error(
            "Config mismatch: polygon base url with massive endpoints",
            base_url=settings.MASSIVE_API_BASE_URL,
            bars_path_template=settings.MASSIVE_BARS_PATH_TEMPLATE,
        )
        raise RuntimeError("Config mismatch: polygon base url with massive endpoints")

    if settings.MASSIVE_API_BASE_URL.endswith("/"):
        logger.warning(
            "Massive base url has trailing slash; recommend removing for consistency",
            base_url=settings.MASSIVE_API_BASE_URL,
        )

    try:
        ZoneInfo(settings.TIMEZONE)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Invalid TIMEZONE: {settings.TIMEZONE}") from exc

    windows = parse_windows(settings.ALLOWED_WINDOWS)
    logger.info(
        "config scan windows",
        windows=[{"start": start.isoformat(), "end": end.isoformat()} for start, end in windows],
    )

    if settings.RTH_ONLY:
        logger.warning(
            "RTH_ONLY is informational; use ALLOWED_WINDOWS/SCAN_OUTSIDE_WINDOW for gating",
            rth_only=settings.RTH_ONLY,
            allowed_windows=settings.ALLOWED_WINDOWS,
        )

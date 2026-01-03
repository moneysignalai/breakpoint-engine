from __future__ import annotations

import os
import sys
from typing import Any

from loguru import logger


def configure_logging(service_name: str) -> None:
    """Configure Loguru with shared settings for web and worker services."""

    level = os.getenv("LOG_LEVEL", "INFO").upper()
    json_logging = os.getenv("LOG_JSON", "false").lower() == "true"

    log_format = (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {extra[service]:<8} | {message}"
    )

    logger.remove()
    logger.configure(
        handlers=[
            {
                "sink": sys.stdout,
                "level": level,
                "format": log_format,
                "serialize": json_logging,
                "enqueue": True,
                "backtrace": False,
                "diagnose": False,
            }
        ],
        extra={"service": service_name},
    )


__all__: list[Any] = ["configure_logging"]

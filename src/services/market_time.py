from __future__ import annotations

from datetime import datetime, time
from typing import List, Tuple
from zoneinfo import ZoneInfo

from src.config import get_settings

settings = get_settings()


def parse_windows(window_str: str) -> List[Tuple[time, time]]:
    windows = []
    for part in window_str.split(','):
        start_s, end_s = part.split('-')
        start = time.fromisoformat(start_s)
        end = time.fromisoformat(end_s)
        windows.append((start, end))
    return windows


def in_allowed_window(now: datetime | None = None) -> bool:
    tz = ZoneInfo(settings.TIMEZONE)
    now = now or datetime.now(tz)
    windows = parse_windows(settings.ALLOWED_WINDOWS)
    for start, end in windows:
        if start <= now.time() <= end:
            return True
    return False


def is_rth(now: datetime | None = None) -> bool:
    tz = ZoneInfo(settings.TIMEZONE)
    now = now or datetime.now(tz)
    return time(9, 30) <= now.time() <= time(16, 0)

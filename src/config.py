from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", case_sensitive=False)

    MASSIVE_API_KEY: str
    DATA_PROVIDER: str = "polygon"
    BASE_URL: str | None = None
    MASSIVE_API_BASE_URL: str = Field(
        default="https://api.polygon.io",
        validation_alias=AliasChoices("MASSIVE_API_BASE_URL", "MASSIVE_BASE_URL"),
    )
    DATABASE_URL: str
    TELEGRAM_ENABLED: bool = Field(default=False)
    TELEGRAM_BOT_TOKEN: str | None = None
    TELEGRAM_CHAT_ID: str | None = None
    DEBUG_MODE: bool = False
    DEBUG_SYMBOL: str | None = None
    TEST_ALERT_ON_START: bool = False
    SCAN_INTERVAL_SECONDS: int = 60
    UNIVERSE: str = "SPY,QQQ,IWM,NVDA,TSLA,AAPL,MSFT,AMZN,META,AMD,AVGO"
    RTH_ONLY: bool = True
    SCAN_OUTSIDE_WINDOW: bool = False
    MIN_CONFIDENCE_TO_ALERT: float = 7.5
    TIMEZONE: str = "America/New_York"

    MASSIVE_BARS_PATH_TEMPLATE: str = "/markets/{symbol}/bars"

    MIN_AVG_DAILY_VOLUME: int = 5_000_000
    MIN_PRICE: float = 10.0
    MAX_PRICE: float = 1000.0
    BOX_BARS: int = 12
    BOX_MAX_RANGE_PCT: float = 0.012
    ATR_COMP_FACTOR: float = 0.75
    VOL_CONTRACTION_FACTOR: float = 0.80
    BREAK_BUFFER_PCT: float = 0.001
    MAX_EXTENSION_PCT: float = 0.006
    BREAK_VOL_MULT: float = 1.5
    VWAP_CONFIRM: bool = True
    SPREAD_PCT_MAX: float = 0.08
    MIN_OPT_VOLUME: int = 200
    MIN_OPT_OI: int = 500
    MIN_OPT_MID: float = 0.25
    IV_PCTL_MAX_FOR_AGG: float = 0.70
    IV_PCTL_MAX_FOR_ANY: float = 0.85
    ALLOWED_WINDOWS: str = "09:35-11:00,13:30-15:50"

    ENTRY_BUFFER_PCT: float = 0.0005
    STOP_BUFFER_PCT: float = 0.0015

    def universe_list(self) -> List[str]:
        return [s.strip().upper() for s in self.UNIVERSE.split(',') if s.strip()]

    def non_secret_dict(self) -> dict:
        data = self.model_dump()
        data.pop('MASSIVE_API_KEY', None)
        data.pop('DATABASE_URL', None)
        return data


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

# Quick self-check:
# python -c "from src.config import get_settings; print(get_settings().model_dump() if hasattr(get_settings(), 'model_dump') else 'ok')"

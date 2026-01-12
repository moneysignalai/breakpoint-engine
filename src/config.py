from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", case_sensitive=False)

    MASSIVE_API_KEY: str
    DATA_PROVIDER: str = "massive"
    BASE_URL: str | None = None
    MASSIVE_API_BASE_URL: str = Field(
        default="https://api.massive.com",
        validation_alias=AliasChoices("MASSIVE_API_BASE_URL"),
    )
    DATABASE_URL: str
    TELEGRAM_ENABLED: bool = Field(default=False)
    TELEGRAM_BOT_TOKEN: str | None = None
    TELEGRAM_CHAT_ID: str | None = None
    DEBUG_MODE: bool = False
    DEBUG_SYMBOL: str | None = None
    DEBUG_LENIENT_MODE: bool = False
    DEBUG_MAX_ALERTS_PER_SCAN: int = 5
    DEV_TEST_MODE: bool = False
    TEST_ALERT_ON_START: bool = False
    SCAN_INTERVAL_SECONDS: int = 60
    UNIVERSE: str = "SPY,QQQ,IWM,NVDA,TSLA,AAPL,MSFT,AMZN,META,AMD,AVGO"
    RTH_ONLY: bool = True
    SCAN_OUTSIDE_WINDOW: bool = False
    ALERT_MODE: str = "TRADE"
    MIN_CONFIDENCE_TO_ALERT: float = 7.0
    MAX_ALERTS_PER_SCAN: int = 6
    MINUTES_BETWEEN_SAME_TICKER: int = 45
    TIMEZONE: str = "America/New_York"

    MASSIVE_BARS_PATH_TEMPLATE: str = "/v1/markets/{symbol}/bars"  # Legacy Massive bars path (unused).

    MIN_AVG_DAILY_VOLUME: int = 5_000_000  # Shares/day; tune down if Massive averages appear lower than expected.
    MIN_PRICE: float = 10.0
    MAX_PRICE: float = 1000.0
    BOX_BARS: int = 12
    MIN_BARS_RTH: int = 36
    MIN_BARS_NON_RTH: int = 18
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
    IV_PCTL_MAX_FOR_AGG: float = 0.70  # 0-1 range (0.70 == 70th percentile).
    IV_PCTL_MAX_FOR_ANY: float = 0.85  # 0-1 range (0.85 == 85th percentile).
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

    @field_validator("IV_PCTL_MAX_FOR_AGG", "IV_PCTL_MAX_FOR_ANY")
    @classmethod
    def _validate_iv_percentile(cls, value: float) -> float:
        if value < 0 or value > 1:
            raise ValueError(
                "IV percentile settings must be 0-1 (e.g., 0.70 for 70th percentile)."
            )
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

# Quick self-check:
# python -c "from src.config import get_settings; print(get_settings().model_dump() if hasattr(get_settings(), 'model_dump') else 'ok')"

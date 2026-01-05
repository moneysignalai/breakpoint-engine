from __future__ import annotations

from datetime import datetime, timedelta
import time
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

import httpx
from loguru import logger

from src.config import get_settings

settings = get_settings()


class MassiveNotFoundError(Exception):
    """Raised when Massive returns a 404 for a given resource."""


class MassiveClient:
    def __init__(self, api_key: str | None = None, timeout: float = 10.0):
        self.api_key = api_key or settings.MASSIVE_API_KEY
        self.timeout = timeout
        self.base_url = settings.MASSIVE_API_BASE_URL or "https://api.massive.com"
        self.bars_path_template = settings.MASSIVE_BARS_PATH_TEMPLATE
        self.client = httpx.Client(
            timeout=httpx.Timeout(timeout, connect=timeout, read=timeout),
            headers={"Authorization": f"Bearer {self.api_key}"},
        )

    def _request(self, method: str, path: str, params: dict | None = None, *, symbol: str | None = None) -> Any:
        backoff = 1.0
        url = f"{self.base_url}{path}"
        retryable_status = {429, 500, 502, 503, 504}
        max_attempts = 3
        for attempt in range(max_attempts):
            start = time.perf_counter()
            try:
                response = self.client.request(method, url, params=params)
            except httpx.RequestError as exc:
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                logger.error(
                    "Massive request error",
                    url=url,
                    symbol=symbol,
                    elapsed_ms=elapsed_ms,
                    error=str(exc),
                    attempt=attempt + 1,
                )
                if attempt < max_attempts - 1:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                raise

            elapsed_ms = int((time.perf_counter() - start) * 1000)
            status_code = response.status_code
            snippet = (response.text or "")[:200]

            if status_code == 404:
                logger.error(
                    "Massive request 404",
                    url=url,
                    symbol=symbol,
                    status_code=status_code,
                    elapsed_ms=elapsed_ms,
                    response_snippet=snippet,
                )
                raise MassiveNotFoundError(f"{method} {path} returned 404")

            if status_code in retryable_status and attempt < max_attempts - 1:
                logger.warning(
                    "Massive request retryable",
                    url=url,
                    symbol=symbol,
                    status_code=status_code,
                    elapsed_ms=elapsed_ms,
                    response_snippet=snippet,
                    attempt=attempt + 1,
                )
                time.sleep(backoff)
                backoff *= 2
                continue

            if status_code != 200:
                logger.error(
                    "Massive request non-200",
                    url=url,
                    symbol=symbol,
                    status_code=status_code,
                    elapsed_ms=elapsed_ms,
                    response_snippet=snippet,
                )
                response.raise_for_status()

            logger.debug(
                "Massive request ok",
                url=url,
                symbol=symbol,
                status_code=status_code,
                elapsed_ms=elapsed_ms,
            )
            return response.json()
        raise RuntimeError("Unreachable")

    def get_bars(self, symbol: str, timeframe: str, limit: int) -> List[Dict[str, Any]]:
        multiplier, timespan, step = self._timeframe_to_range(timeframe)
        ny_tz = ZoneInfo("America/New_York")
        now = datetime.now(ny_tz)
        buffer = timedelta(minutes=30)
        window = step * limit + buffer
        start_at = now - window
        path = (
            f"/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/"
            f"{start_at.isoformat()}/{now.isoformat()}"
        )

        data = self._request(
            "GET",
            path,
            symbol=symbol,
        )
        raw_bars = data.get("results", data) if isinstance(data, dict) else data
        bars: List[Dict[str, Any]] = []
        for bar in raw_bars or []:
            normalized_bar = dict(bar)
            normalized_bar.setdefault("t", bar.get("t") or bar.get("timestamp") or bar.get("ts"))
            normalized_bar.setdefault("o", bar.get("o"))
            normalized_bar.setdefault("h", bar.get("h"))
            normalized_bar.setdefault("l", bar.get("l"))
            normalized_bar.setdefault("c", bar.get("c"))
            normalized_bar.setdefault("v", bar.get("v"))
            bars.append(normalized_bar)
        return bars

    def _timeframe_to_range(self, timeframe: str) -> tuple[int, str, timedelta]:
        if timeframe == "5m":
            return 5, "minute", timedelta(minutes=5)
        if timeframe == "1d":
            return 1, "day", timedelta(days=1)
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    def get_daily_snapshot(self, symbol: str) -> Dict[str, Any]:
        data = self._request(
            "GET",
            f"/markets/{symbol}/snapshot",
            params={"timeframe": "1d", "limit": 1},
            symbol=symbol,
        )
        if isinstance(data, dict):
            return data
        return data[0] if data else {}

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        return self._request("GET", f"/markets/{symbol}/quote", symbol=symbol)

    def get_option_expirations(self, symbol: str) -> List[str]:
        data = self._request("GET", f"/options/{symbol}/expirations", symbol=symbol)
        return data.get("expirations", data)

    def get_option_chain(self, symbol: str, expiration: str) -> List[Dict[str, Any]]:
        data = self._request(
            "GET",
            f"/options/{symbol}/chain",
            params={"expiration": expiration},
            symbol=symbol,
        )
        return data.get("contracts", data)

    def close(self) -> None:
        self.client.close()

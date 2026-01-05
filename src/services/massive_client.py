from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
        url = path if path.startswith("http") else f"{self.base_url}{path}"
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
            snippet = (response.text or "")[:300]

            if status_code == 404:
                logger.error(
                    "Massive request 404",
                    method=method,
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
                    method=method,
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
                    method=method,
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

        def to_epoch_ms(dt: datetime) -> int:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt_utc = dt.astimezone(timezone.utc)
            return int(dt_utc.timestamp() * 1000)

        from_ms = to_epoch_ms(start_at)
        to_ms = to_epoch_ms(now)

        # Massive agg endpoint requires epoch milliseconds (not ISO strings) in the path
        path = f"/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{from_ms}/{to_ms}"

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
        minute_map = {
            "1m": 1,
            "5m": 5,
            "15m": 15,
            "30m": 30,
            "60m": 60,
        }
        if timeframe in minute_map:
            minutes = minute_map[timeframe]
            return minutes, "minute", timedelta(minutes=minutes)
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
        path = "/v3/reference/options/contracts"
        params: Dict[str, Any] = {
            "underlying_ticker": symbol,
            "expired": "false",
            "limit": 1000,
            "sort": "expiration_date",
        }

        expirations: set[str] = set()
        next_path: str | None = path
        next_params: Dict[str, Any] | None = params

        while next_path:
            data = self._request("GET", next_path, params=next_params, symbol=symbol)
            for contract in data.get("results", []) or []:
                exp = contract.get("expiration_date")
                if exp:
                    expirations.add(exp)

            next_url = data.get("next_url") if isinstance(data, dict) else None
            if next_url:
                next_path = next_url.replace(self.base_url, "")
                next_params = None
            else:
                next_path = None

        return sorted(expirations)

    def get_option_chain(self, symbol: str, expiration: str) -> List[Dict[str, Any]]:
        path = "/v3/reference/options/contracts"
        params: Dict[str, Any] = {
            "underlying_ticker": symbol,
            "expired": "false",
            "expiration_date": expiration,
            "limit": 1000,
            "sort": "strike_price",
        }

        contracts: List[Dict[str, Any]] = []
        next_path: str | None = path
        next_params: Dict[str, Any] | None = params

        while next_path:
            data = self._request("GET", next_path, params=next_params, symbol=symbol)
            for contract in data.get("results", []) or []:
                contracts.append(
                    {
                        "ticker": contract.get("ticker") or contract.get("contract_symbol"),
                        "contract_symbol": contract.get("ticker") or contract.get("contract_symbol"),
                        "strike_price": contract.get("strike_price"),
                        "expiration_date": contract.get("expiration_date"),
                        "contract_type": contract.get("contract_type"),
                    }
                )

            next_url = data.get("next_url") if isinstance(data, dict) else None
            if next_url:
                next_path = next_url.replace(self.base_url, "")
                next_params = None
            else:
                next_path = None

        return contracts

    def close(self) -> None:
        self.client.close()

from __future__ import annotations

from datetime import datetime
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
        self.provider = (settings.DATA_PROVIDER or "polygon").lower()
        self.base_url = self._resolve_base_url()
        self.bars_path_template = settings.MASSIVE_BARS_PATH_TEMPLATE
        self.client = httpx.Client(
            timeout=httpx.Timeout(timeout, connect=timeout, read=timeout),
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        if self.provider == "polygon" and "polygon" not in self.base_url:
            logger.warning(
                "provider/base_url mismatch",
                provider=self.provider,
                base_url=self.base_url,
            )

    def _resolve_base_url(self) -> str:
        if settings.BASE_URL:
            return settings.BASE_URL
        if self.provider == "polygon":
            return "https://api.polygon.io"
        if self.provider == "massive":
            return settings.MASSIVE_API_BASE_URL or "https://api.massive.com"
        return settings.MASSIVE_API_BASE_URL or "https://api.massive.com"

    def _request(self, method: str, path: str, params: dict | None = None, *, symbol: str | None = None) -> Any:
        backoff = 1.0
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        endpoint = path if path.startswith("/") else path.replace(self.base_url, "")
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
                    path=endpoint,
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
            full_url = str(response.request.url) if response.request else url

            if status_code == 404:
                safe_params = dict(params or {})
                safe_params.pop("apiKey", None)
                safe_params.pop("apikey", None)
                logger.warning(
                    "Massive request 404",
                    method=method,
                    path=endpoint,
                    url=full_url,
                    params=safe_params or None,
                    symbol=symbol,
                    status_code=status_code,
                    elapsed_ms=elapsed_ms,
                    response_snippet=snippet,
                )
                err = MassiveNotFoundError(f"{method} {path} returned 404")
                err.request = response.request
                err.response = response
                raise err

            if status_code in retryable_status and attempt < max_attempts - 1:
                logger.warning(
                    "Massive request retryable",
                    method=method,
                    path=endpoint,
                    url=full_url,
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
                logger.warning(
                    "Massive request non-200",
                    method=method,
                    path=endpoint,
                    url=full_url,
                    symbol=symbol,
                    status_code=status_code,
                    elapsed_ms=elapsed_ms,
                    response_snippet=snippet,
                )
                response.raise_for_status()

            logger.debug(
                "Massive request ok",
                path=endpoint,
                symbol=symbol,
                status_code=status_code,
                elapsed_ms=elapsed_ms,
            )
            return response.json()
        raise RuntimeError("Unreachable")

    def get_bars(self, symbol: str, timeframe: str, limit: int) -> List[Dict[str, Any]]:
        multiplier, timespan = self._timeframe_to_range(timeframe)
        ny_tz = ZoneInfo("America/New_York")
        now = datetime.now(ny_tz)
        from_date = now.strftime("%Y-%m-%d")
        to_date = now.strftime("%Y-%m-%d")

        if self.provider == "polygon":
            path = f"/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{from_date}/{to_date}"
            params = {"adjusted": True, "sort": "desc", "limit": limit}
        else:
            path = self.bars_path_template.format(symbol=symbol)
            params = {"timeframe": timeframe, "limit": limit}

        data = self._request(
            "GET",
            path,
            params=params,
            symbol=symbol,
        )
        raw_bars = data.get("results", data) if isinstance(data, dict) else data
        bars: List[Dict[str, Any]] = []
        for bar in raw_bars or []:
            normalized_bar = dict(bar)
            normalized_bar.setdefault("t", bar.get("t") or bar.get("timestamp") or bar.get("ts"))
            normalized_bar.setdefault("o", bar.get("o") or bar.get("open"))
            normalized_bar.setdefault("h", bar.get("h") or bar.get("high"))
            normalized_bar.setdefault("l", bar.get("l") or bar.get("low"))
            normalized_bar.setdefault("c", bar.get("c") or bar.get("close"))
            normalized_bar.setdefault("v", bar.get("v") or bar.get("volume"))
            bars.append(normalized_bar)
        return bars

    def _timeframe_to_range(self, timeframe: str) -> tuple[int, str]:
        if timeframe == "1m":
            return 1, "minute"
        if timeframe == "5m":
            return 5, "minute"
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    def get_daily_snapshot(self, symbol: str) -> Dict[str, Any]:
        if self.provider == "polygon":
            path = f"/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}"
        else:
            path = f"/markets/{symbol}/snapshot"

        data = self._request(
            "GET",
            path,
            symbol=symbol,
        )

        if not isinstance(data, dict):
            return {"avg_daily_volume": None, "volume": None, "iv_percentile": None, "raw": data}

        ticker_data = data.get("ticker") if isinstance(data.get("ticker"), dict) else None
        if ticker_data is None:
            ticker_data = data if isinstance(data, dict) else None

        if not isinstance(ticker_data, dict):
            return {"avg_daily_volume": None, "volume": None, "iv_percentile": None, "raw": data}

        day = ticker_data.get("day") or ticker_data.get("today") or {}

        snapshot = {
            "avg_daily_volume": ticker_data.get("avg_daily_volume")
            or ticker_data.get("avgDailyVolume")
            or day.get("v"),
            "volume": day.get("v")
            or ticker_data.get("volume")
            or ticker_data.get("v"),
            "iv_percentile": ticker_data.get("iv_percentile")
            or ticker_data.get("ivPercentile"),
            "raw": data,
        }

        for key, value in snapshot.items():
            if key != "raw" and value is None:
                snapshot[key] = None

        return snapshot

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

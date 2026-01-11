from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping

import httpx
from loguru import logger

from src.config import get_settings
from src.strategies.flagship import Bar

settings = get_settings()


class MassiveAPIError(Exception):
    """Raised when Massive returns a non-200 response."""

    def __init__(self, message: str, *, status_code: int, url: str, response: httpx.Response | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.url = url
        self.response = response


class MassiveNotFoundError(MassiveAPIError):
    """Raised when Massive returns a 404 for a given resource."""


class MassiveClient:
    def __init__(self, api_key: str | None = None, timeout: float = 10.0):
        self.api_key = api_key or settings.MASSIVE_API_KEY
        self.timeout = timeout
        self.provider = (settings.DATA_PROVIDER or "polygon").lower()
        self.base_url, self.base_url_source = self._resolve_base_url()
        self.bars_path_template = settings.MASSIVE_BARS_PATH_TEMPLATE
        self.client = httpx.Client(timeout=httpx.Timeout(timeout, connect=timeout, read=timeout))
        if self.provider == "polygon" and "polygon" not in self.base_url:
            logger.warning(
                "provider/base_url mismatch",
                provider=self.provider,
                base_url=self.base_url,
            )

    def _resolve_base_url(self) -> tuple[str, str]:
        env_api_base = os.getenv("MASSIVE_API_BASE_URL")

        if settings.BASE_URL:
            return settings.BASE_URL.rstrip("/"), "BASE_URL"
        if self.provider == "polygon":
            if env_api_base:
                return env_api_base.rstrip("/"), "MASSIVE_API_BASE_URL"
            if settings.MASSIVE_API_BASE_URL and "polygon" in settings.MASSIVE_API_BASE_URL:
                return settings.MASSIVE_API_BASE_URL.rstrip("/"), "MASSIVE_API_BASE_URL"
            return "https://api.polygon.io", "default"
        if self.provider == "massive":
            if env_api_base:
                return env_api_base.rstrip("/"), "MASSIVE_API_BASE_URL"
            return (settings.MASSIVE_API_BASE_URL or "https://api.massive.com").rstrip("/"), "default"
        return (settings.MASSIVE_API_BASE_URL or "https://api.massive.com").rstrip("/"), "default"

    def _safe_params(self, params: Mapping[str, Any] | None) -> Dict[str, Any]:
        safe_params = dict(params or {})
        for key in ("apiKey", "apikey", "api_key", "x-api-key", "token"):
            safe_params.pop(key, None)
        return safe_params

    def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        *,
        symbol: str | None = None,
        run_id: str | None = None,
        raise_for_status: bool = False,
    ) -> Any:
        backoff = 1.0
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        endpoint = path if path.startswith("/") else path.replace(self.base_url, "")
        retryable_status = {429, 500, 502, 503, 504}
        max_attempts = 3
        request_params = dict(params or {})
        if self.api_key:
            request_params.setdefault("apiKey", self.api_key)
        for attempt in range(max_attempts):
            start = time.perf_counter()
            try:
                response = self.client.request(method, url, params=request_params)
            except httpx.RequestError as exc:
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                logger.warning(
                    "Massive request error",
                    provider=self.provider,
                    path=endpoint,
                    url=url,
                    params=self._safe_params(request_params) or None,
                    symbol=symbol,
                    elapsed_ms=elapsed_ms,
                    error=str(exc),
                    run_id=run_id,
                    attempt=attempt + 1,
                )
                if attempt < max_attempts - 1:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                return None

            elapsed_ms = int((time.perf_counter() - start) * 1000)
            status_code = response.status_code
            snippet = (response.text or "")[:500]
            full_url = str(response.request.url) if response.request else url
            safe_params = self._safe_params(request_params)

            if status_code == 404:
                logger.warning(
                    "Massive request failed",
                    method=method,
                    provider=self.provider,
                    path=endpoint,
                    url=full_url,
                    params=safe_params or None,
                    symbol=symbol,
                    status_code=status_code,
                    elapsed_ms=elapsed_ms,
                    body_snippet=snippet,
                    run_id=run_id,
                )
                if raise_for_status:
                    raise MassiveNotFoundError(
                        "Massive request failed with 404",
                        status_code=status_code,
                        url=full_url,
                        response=response,
                    )
                return None

            if status_code in retryable_status and attempt < max_attempts - 1:
                logger.warning(
                    "Massive request retryable",
                    method=method,
                    provider=self.provider,
                    path=endpoint,
                    url=full_url,
                    symbol=symbol,
                    status_code=status_code,
                    elapsed_ms=elapsed_ms,
                    body_snippet=snippet,
                    run_id=run_id,
                    attempt=attempt + 1,
                )
                time.sleep(backoff)
                backoff *= 2
                continue

            if status_code < 200 or status_code >= 300:
                logger.error(
                    "Massive request failed",
                    error_code="massive_http_error",
                    method=method,
                    provider=self.provider,
                    url=full_url,
                    params=safe_params or None,
                    symbol=symbol,
                    status_code=status_code,
                    elapsed_ms=elapsed_ms,
                    body_snippet=snippet,
                    run_id=run_id,
                )
                if raise_for_status:
                    raise MassiveAPIError(
                        "Massive request failed",
                        status_code=status_code,
                        url=full_url,
                        response=response,
                    )
                if 400 <= status_code < 500:
                    return None
                if status_code in retryable_status and attempt < max_attempts - 1:
                    continue
                return None

            logger.debug(
                "Massive request ok",
                method=method,
                path=endpoint,
                symbol=symbol,
                status_code=status_code,
                elapsed_ms=elapsed_ms,
                run_id=run_id,
            )
            try:
                return response.json()
            except ValueError:
                logger.warning(
                    "Massive response non-json",
                    provider=self.provider,
                    path=endpoint,
                    symbol=symbol,
                    status_code=status_code,
                    elapsed_ms=elapsed_ms,
                    response_snippet=snippet,
                    run_id=run_id,
                )
                if raise_for_status:
                    raise MassiveAPIError(
                        "Massive response was not JSON",
                        status_code=status_code,
                        url=full_url,
                        response=response,
                    )
                return None
        return None

    @staticmethod
    def _extract_list(payload: Any, keys: tuple[str, ...]) -> List[Dict[str, Any]]:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in keys:
                value = payload.get(key)
                if isinstance(value, list):
                    return value
        return []

    @staticmethod
    def _ts_ms_to_dt(ts_ms: int) -> datetime:
        return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)

    def get_bars(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
        adjusted: bool = True,
        run_id: str | None = None,
    ) -> List[Bar]:
        if timeframe != "5m":
            raise ValueError(f"Unsupported timeframe={timeframe!r}; only '5m' is implemented")

        multiplier = 5
        timespan = "minute"
        now = datetime.now(timezone.utc)
        from_dt = now - timedelta(days=5)
        from_date = from_dt.date().isoformat()
        to_date = now.date().isoformat()

        path = f"/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{from_date}/{to_date}"
        params = {
            "adjusted": "true" if adjusted else "false",
            "sort": "asc",
            "limit": limit * 4,
        }

        data = self._request("GET", path, params=params, symbol=symbol, run_id=run_id)
        results = data.get("results") if isinstance(data, dict) else None
        bars: List[Bar] = []
        for r in results or []:
            bars.append(
                Bar(
                    ts=self._ts_ms_to_dt(r["t"]),
                    open=r["o"],
                    high=r["h"],
                    low=r["l"],
                    close=r["c"],
                    volume=r["v"],
                )
            )

        return bars[-limit:]

    def get_daily_snapshot(self, symbol: str) -> Dict[str, Any]:
        if self.provider == "polygon":
            path = f"/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}"
        else:
            path = f"/v1/markets/{symbol}/snapshot"

        data = self._request(
            "GET",
            path,
            symbol=symbol,
        )

        if data is None:
            return {"avg_daily_volume": None, "volume": None, "iv_percentile": None, "raw": None}
        if not isinstance(data, dict):
            return {"avg_daily_volume": None, "volume": None, "iv_percentile": None, "raw": data}

        if isinstance(data.get("data"), dict):
            ticker_data = data.get("data")
        else:
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
        path = f"/v3/snapshot/stocks/{symbol}"
        data = self._request("GET", path, symbol=symbol, raise_for_status=True)
        return data or {}

    def get_option_expirations(self, symbol: str) -> List[str]:
        if self.provider == "polygon":
            path = "/v3/reference/options/contracts"
            params: Dict[str, Any] = {
                "underlying_ticker": symbol,
                "expired": "false",
                "limit": 1000,
                "sort": "expiration_date",
            }
        else:
            path = "/v1/options/expirations"
            params = {
                "symbol": symbol,
                "include_expired": False,
                "limit": 500,
            }

        expirations: set[str] = set()
        next_path: str | None = path
        next_params: Dict[str, Any] | None = params

        while next_path:
            data = self._request("GET", next_path, params=next_params, symbol=symbol)
            if not data:
                break
            results = self._extract_list(data, ("results", "data", "expirations"))
            if results:
                for contract in results:
                    if isinstance(contract, str):
                        expirations.add(contract)
                        continue
                    exp = contract.get("expiration_date") or contract.get("expiration")
                    if exp:
                        expirations.add(exp)
            elif isinstance(data, dict):
                exp = data.get("expiration_date") or data.get("expiration")
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
        if self.provider == "polygon":
            path = "/v3/reference/options/contracts"
            params: Dict[str, Any] = {
                "underlying_ticker": symbol,
                "expired": "false",
                "expiration_date": expiration,
                "limit": 1000,
                "sort": "strike_price",
            }
        else:
            path = "/v1/options/contracts"
            params = {
                "symbol": symbol,
                "expiration": expiration,
                "limit": 1000,
                "sort": "strike_price",
            }

        contracts: List[Dict[str, Any]] = []
        next_path: str | None = path
        next_params: Dict[str, Any] | None = params

        while next_path:
            data = self._request("GET", next_path, params=next_params, symbol=symbol)
            if not data:
                break
            for contract in self._extract_list(data, ("results", "data", "contracts")):
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

    def health_check(self, symbol: str = "SPY") -> Dict[str, Any]:
        symbol = symbol.upper()
        logger.info(
            "Massive health check",
            provider=self.provider,
            base_url=self.base_url,
            symbol=symbol,
        )
        try:
            quote = self.get_quote(symbol)
        except MassiveAPIError as exc:
            logger.warning(
                "Massive health check failed",
                provider=self.provider,
                base_url=self.base_url,
                symbol=symbol,
                status_code=exc.status_code,
                error=str(exc),
            )
            return {"ok": False, "status_code": exc.status_code, "message": str(exc)}
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Massive health check failed",
                provider=self.provider,
                base_url=self.base_url,
                symbol=symbol,
                error=str(exc),
            )
            return {"ok": False, "status_code": None, "message": str(exc)}

        ok = bool(quote)
        logger.info(
            "Massive health check result",
            provider=self.provider,
            base_url=self.base_url,
            symbol=symbol,
            ok=ok,
        )
        return {"ok": ok, "status_code": 200 if ok else None, "message": "ok" if ok else "empty response"}

    def close(self) -> None:
        self.client.close()

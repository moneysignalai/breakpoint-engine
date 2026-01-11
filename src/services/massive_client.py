from __future__ import annotations

import math
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Mapping
from zoneinfo import ZoneInfo

import httpx
from loguru import logger

from src.config import get_settings

settings = get_settings()


class MassiveNotFoundError(Exception):
    """Raised when Massive returns a 404 for a given resource."""


class MassiveHTTPError(Exception):
    """Raised when Massive returns a non-200 response."""

    def __init__(self, message: str, *, status_code: int, url: str, response: httpx.Response | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.url = url
        self.response = response


class MassiveClient:
    def __init__(self, api_key: str | None = None, timeout: float = 10.0):
        self.api_key = api_key or settings.MASSIVE_API_KEY
        self.timeout = timeout
        self.provider = (settings.DATA_PROVIDER or "polygon").lower()
        self.base_url, self.base_url_source = self._resolve_base_url()
        self.bars_path_template = settings.MASSIVE_BARS_PATH_TEMPLATE
        self.client = httpx.Client(
            timeout=httpx.Timeout(timeout, connect=timeout, read=timeout),
            headers=self._auth_headers(),
        )
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

    def _auth_headers(self) -> Mapping[str, str]:
        if not self.api_key:
            return {}
        return {"X-API-KEY": self.api_key}

    def _safe_params(self, params: Mapping[str, Any] | None) -> Dict[str, Any]:
        safe_params = dict(params or {})
        for key in ("apiKey", "apikey", "api_key", "x-api-key", "token"):
            safe_params.pop(key, None)
        return safe_params

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
                logger.warning(
                    "Massive request error",
                    provider=self.provider,
                    path=endpoint,
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
                return None

            elapsed_ms = int((time.perf_counter() - start) * 1000)
            status_code = response.status_code
            snippet = (response.text or "")[:500]
            full_url = str(response.request.url) if response.request else url
            safe_params = self._safe_params(params)

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

    def get_bars(self, symbol: str, timeframe: str, limit: int) -> List[Dict[str, Any]]:
        multiplier, timespan = self._timeframe_to_range(timeframe)
        ny_tz = ZoneInfo("America/New_York")
        now = datetime.now(ny_tz)
        session = "rth" if settings.RTH_ONLY else "all"
        approx_minutes = limit * multiplier
        from_dt = now - timedelta(minutes=approx_minutes * 2)
        to_dt = now

        def normalize_bars(raw: List[Dict[str, Any]] | Dict[str, Any]) -> List[Dict[str, Any]]:
            raw_bars = self._extract_list(raw, ("results", "data", "bars", "candles"))
            normalized: List[Dict[str, Any]] = []
            for bar in raw_bars or []:
                normalized_bar = dict(bar)
                normalized_bar.setdefault("t", bar.get("t") or bar.get("timestamp") or bar.get("ts"))
                normalized_bar.setdefault("o", bar.get("o") or bar.get("open"))
                normalized_bar.setdefault("h", bar.get("h") or bar.get("high"))
                normalized_bar.setdefault("l", bar.get("l") or bar.get("low"))
                normalized_bar.setdefault("c", bar.get("c") or bar.get("close"))
                normalized_bar.setdefault("v", bar.get("v") or bar.get("volume"))
                normalized.append(normalized_bar)
            return normalized

        if self.provider == "polygon":
            def _ts_key(bar: Dict[str, Any]) -> Any:
                ts = bar.get("t") or bar.get("ts") or bar.get("timestamp")
                if isinstance(ts, datetime):
                    return ts
                if isinstance(ts, str):
                    try:
                        return datetime.fromisoformat(ts)
                    except Exception:  # noqa: BLE001
                        return ts
                return ts or 0

            def fetch_polygon_bars(from_date: str, api_limit: int) -> List[Dict[str, Any]]:
                path = f"/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{from_date}/{to_date}"
                params = {"adjusted": True, "sort": "desc", "limit": api_limit}
                data = self._request(
                    "GET",
                    path,
                    params=params,
                    symbol=symbol,
                )
                bars = normalize_bars(data)
                sorted_bars = sorted(bars, key=_ts_key)
                from_dt_parsed = datetime.fromisoformat(from_date).date()
                to_dt_parsed = datetime.fromisoformat(to_date).date()
                requested_range_days = (to_dt_parsed - from_dt_parsed).days + 1
                sliced = sorted_bars[-limit:]
                logger.info(
                    "bars fetched | symbol={symbol} provider=polygon timeframe={tf} "
                    "requested={requested} raw_returned={raw_returned} "
                    "final_returned={final_returned} from={from_date} to={to_date} "
                    "requested_range_days={requested_range_days}",
                    symbol=symbol,
                    tf=timeframe,
                    requested=limit,
                    raw_returned=len(sorted_bars),
                    final_returned=len(sliced),
                    from_date=from_date,
                    to_date=to_date,
                    requested_range_days=requested_range_days,
                )
                return sorted_bars

            min_bars_setting = getattr(settings, "MIN_BARS", limit)
            desired_min = min(limit, max(min_bars_setting, 10))
            api_limit = max(limit * 3, limit)
            lookbacks = [0, 2, 5, 10]
            attempt_dates = []
            for days in lookbacks:
                attempt_dt = from_dt - timedelta(days=days)
                attempt_dates.append(attempt_dt.date().isoformat())

            bars: List[Dict[str, Any]] = []
            for attempt_from_date in dict.fromkeys(attempt_dates):
                bars = fetch_polygon_bars(attempt_from_date, api_limit)
                if len(bars) >= desired_min:
                    break

            return bars[-limit:]

        minutes_per_day = 390 if session == "rth" else 24 * 60
        bars_per_day = max(1, minutes_per_day // multiplier)
        days = max(1, math.ceil(limit / bars_per_day))
        path = self.bars_path_template.format(symbol=symbol)

        attempts = [days]
        if days < 5:
            attempts.append(5)
        if days < 10:
            attempts.append(10)

        last_bars: List[Dict[str, Any]] = []
        for idx, attempt_days in enumerate(attempts):
            attempt_from_dt = now - timedelta(days=attempt_days)
            data = self._request(
                "GET",
                path,
                params={
                    "multiplier": multiplier,
                    "timespan": timespan,
                    "from": attempt_from_dt.isoformat(),
                    "to": to_dt.isoformat(),
                    "limit": limit,
                    "session": session,
                    "sort": "asc",
                },
                symbol=symbol,
            )
            if data is None:
                logger.warning(
                    "bars fetch returned no data",
                    provider=self.provider,
                    symbol=symbol,
                    days=attempt_days,
                    path=path,
                )
                return []

            last_bars = normalize_bars(data)
            returned = len(last_bars)
            logger.info(
                "bars fetched | symbol={symbol} provider=massive timeframe={tf} "
                "requested={requested} returned={returned} days={days} session={session}",
                symbol=symbol,
                tf=timeframe,
                requested=limit,
                returned=returned,
                days=attempt_days,
                session=session,
            )

            has_enough = returned >= limit
            is_last_attempt = idx == len(attempts) - 1
            if has_enough or is_last_attempt:
                break

            next_days = attempts[idx + 1]
            if returned < limit:
                logger.info(
                    "bars refetch | symbol={symbol} requested={requested} returned={returned} "
                    "days={current} -> days={next_days}",
                    symbol=symbol,
                    requested=limit,
                    returned=returned,
                    current=attempt_days,
                    next_days=next_days,
                )

        return last_bars[-limit:]

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
        path = f"/v1/markets/{symbol}/quote" if self.provider == "massive" else f"/v2/last/trade/{symbol}"
        data = self._request("GET", path, symbol=symbol)
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

    def health_check(self, symbol: str = "SPY") -> bool:
        symbol = symbol.upper()
        logger.info(
            "Massive health check",
            provider=self.provider,
            base_url=self.base_url,
            symbol=symbol,
        )
        try:
            quote = self.get_quote(symbol)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Massive health check failed",
                provider=self.provider,
                base_url=self.base_url,
                symbol=symbol,
                error=str(exc),
            )
            return False

        ok = bool(quote)
        logger.info(
            "Massive health check result",
            provider=self.provider,
            base_url=self.base_url,
            symbol=symbol,
            ok=ok,
        )
        return ok

    def close(self) -> None:
        self.client.close()

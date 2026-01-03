from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import httpx
from loguru import logger

from src.config import get_settings

settings = get_settings()


class MassiveClient:
    def __init__(self, api_key: str | None = None, timeout: float = 10.0):
        self.api_key = api_key or settings.MASSIVE_API_KEY
        self.timeout = timeout
        self.base_url = "https://api.massive.app"
        self.client = httpx.Client(timeout=self.timeout, headers={"Authorization": f"Bearer {self.api_key}"})

    def _request(self, method: str, path: str, params: dict | None = None) -> Any:
        backoff = 1.0
        for attempt in range(3):
            start = time.perf_counter()
            try:
                response = self.client.request(method, f"{self.base_url}{path}", params=params)
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                if response.status_code != 200:
                    snippet = response.text[:300] if response.text else ""
                    logger.warning(
                        "Massive request non-200",
                        endpoint=path,
                        status_code=response.status_code,
                        elapsed_ms=elapsed_ms,
                        response_snippet=snippet,
                    )
                response.raise_for_status()
                logger.debug(
                    "Massive request ok",
                    endpoint=path,
                    status_code=response.status_code,
                    elapsed_ms=elapsed_ms,
                )
                return response.json()
            except Exception as exc:  # noqa: BLE001
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                snippet = ""
                if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
                    snippet = exc.response.text[:300]
                logger.warning(
                    "Massive request error",
                    endpoint=path,
                    status_code=getattr(getattr(exc, "response", None), "status_code", None),
                    elapsed_ms=elapsed_ms,
                    error=str(exc),
                    response_snippet=snippet,
                    attempt=attempt + 1,
                )
                if attempt == 2:
                    raise
                time.sleep(backoff)
                backoff *= 2
        raise RuntimeError("Unreachable")

    def get_bars(self, symbol: str, timeframe: str, limit: int) -> List[Dict[str, Any]]:
        data = self._request("GET", f"/markets/{symbol}/bars", params={"timeframe": timeframe, "limit": limit})
        return data.get("bars", data)

    def get_daily_snapshot(self, symbol: str) -> Dict[str, Any]:
        data = self._request("GET", f"/markets/{symbol}/snapshot", params={"timeframe": "1d", "limit": 1})
        if isinstance(data, dict):
            return data
        return data[0] if data else {}

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        return self._request("GET", f"/markets/{symbol}/quote")

    def get_option_expirations(self, symbol: str) -> List[str]:
        data = self._request("GET", f"/options/{symbol}/expirations")
        return data.get("expirations", data)

    def get_option_chain(self, symbol: str, expiration: str) -> List[Dict[str, Any]]:
        data = self._request("GET", f"/options/{symbol}/chain", params={"expiration": expiration})
        return data.get("contracts", data)

    def close(self) -> None:
        self.client.close()

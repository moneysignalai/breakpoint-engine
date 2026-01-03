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
            try:
                response = self.client.request(method, f"{self.base_url}{path}", params=params)
                response.raise_for_status()
                return response.json()
            except Exception as exc:  # noqa: BLE001
                logger.error(f"Massive API error {path} attempt {attempt+1}: {exc}")
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

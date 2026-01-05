from __future__ import annotations

import httpx

from src.services.massive_client import MassiveClient


def test_get_bars_returns_list():
    results = [{"t": 1, "o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5, "v": 100}]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.startswith("/v2/aggs/ticker/SPY/range/5/minute/")
        return httpx.Response(200, json={"results": results})

    transport = httpx.MockTransport(handler)

    client = MassiveClient(api_key="test", timeout=1.0)
    client.base_url = "https://example.com"
    client.client = httpx.Client(transport=transport, headers=client.client.headers)

    bars = client.get_bars("SPY", "5m", 36)

    assert isinstance(bars, list)
    assert bars[0]["t"] == 1

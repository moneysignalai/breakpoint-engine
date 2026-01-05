from __future__ import annotations

import httpx
import httpx

from src.services.massive_client import MassiveClient


def test_get_bars_returns_list():
    results = [{"t": 1, "o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5, "v": 100}]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.startswith("/v2/aggs/ticker/SPY/range/5/minute/")
        parts = request.url.path.rstrip("/").split("/")
        assert len(parts) >= 9
        from_date = parts[-2]
        to_date = parts[-1]
        assert from_date == to_date
        assert len(from_date) == 10
        assert len(to_date) == 10
        assert from_date.count("-") == 2
        assert to_date.count("-") == 2

        assert request.url.params["adjusted"].lower() == "true"
        assert request.url.params["sort"] == "desc"
        assert request.url.params["limit"] == "36"
        return httpx.Response(200, json={"results": results})

    transport = httpx.MockTransport(handler)

    client = MassiveClient(api_key="test", timeout=1.0)
    client.base_url = "https://example.com"
    client.client = httpx.Client(transport=transport, headers=client.client.headers)

    bars = client.get_bars("SPY", "5m", 36)

    assert isinstance(bars, list)
    assert bars[0]["t"] == 1


def test_get_option_expirations_uses_reference_contracts_with_pagination():
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            assert request.url.path == "/v3/reference/options/contracts"
            assert request.url.params["underlying_ticker"] == "SPY"
            data = {
                "results": [
                    {"expiration_date": "2024-01-19"},
                    {"expiration_date": "2024-02-16"},
                ],
                "next_url": "https://example.com/v3/reference/options/contracts?page=2",
            }
            return httpx.Response(200, json=data)

        assert request.url.path == "/v3/reference/options/contracts"
        assert request.url.params["page"] == "2"
        data = {
            "results": [
                {"expiration_date": "2024-03-15"},
                {"expiration_date": "2024-02-16"},
            ]
        }
        return httpx.Response(200, json=data)

    transport = httpx.MockTransport(handler)
    client = MassiveClient(api_key="test", timeout=1.0)
    client.base_url = "https://example.com"
    client.client = httpx.Client(transport=transport, headers=client.client.headers)

    expirations = client.get_option_expirations("SPY")

    assert expirations == ["2024-01-19", "2024-02-16", "2024-03-15"]
    assert call_count == 2


def test_get_option_chain_uses_reference_contracts_with_pagination():
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            assert request.url.path == "/v3/reference/options/contracts"
            assert request.url.params["expiration_date"] == "2024-02-16"
            data = {
                "results": [
                    {
                        "ticker": "SPY240216C00450000",
                        "strike_price": 450,
                        "expiration_date": "2024-02-16",
                        "contract_type": "call",
                    }
                ],
                "next_url": "https://example.com/v3/reference/options/contracts?page=2",
            }
            return httpx.Response(200, json=data)

        assert request.url.params["page"] == "2"
        data = {
            "results": [
                {
                    "contract_symbol": "SPY240216P00450000",
                    "strike_price": 450,
                    "expiration_date": "2024-02-16",
                    "contract_type": "put",
                }
            ]
        }
        return httpx.Response(200, json=data)

    transport = httpx.MockTransport(handler)
    client = MassiveClient(api_key="test", timeout=1.0)
    client.base_url = "https://example.com"
    client.client = httpx.Client(transport=transport, headers=client.client.headers)

    chain = client.get_option_chain("SPY", "2024-02-16")

    assert chain == [
        {
            "ticker": "SPY240216C00450000",
            "contract_symbol": "SPY240216C00450000",
            "strike_price": 450,
            "expiration_date": "2024-02-16",
            "contract_type": "call",
        },
        {
            "ticker": "SPY240216P00450000",
            "contract_symbol": "SPY240216P00450000",
            "strike_price": 450,
            "expiration_date": "2024-02-16",
            "contract_type": "put",
        },
    ]
    assert call_count == 2

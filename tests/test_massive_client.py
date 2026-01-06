from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from src.services.massive_client import MassiveClient


def _set_fixed_datetime(monkeypatch, fixed_dt: datetime) -> None:
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            if tz:
                return fixed_dt.astimezone(tz)
            return fixed_dt

    monkeypatch.setattr("src.services.massive_client.datetime", FixedDateTime)


def test_get_bars_returns_list(monkeypatch):
    results = [{"t": i, "o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5, "v": 100} for i in range(60)]

    fixed_now = datetime(2026, 1, 5, 0, 30, tzinfo=ZoneInfo("America/New_York"))
    _set_fixed_datetime(monkeypatch, fixed_now)

    call_count = 0
    from_dates: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        assert request.url.path.startswith("/v2/aggs/ticker/SPY/range/5/minute/")
        parts = request.url.path.rstrip("/").split("/")
        from_date = parts[-2]
        to_date = parts[-1]
        from_dates.append(from_date)
        assert to_date == "2026-01-05"
        from_dt = datetime.fromisoformat(from_date).date()
        to_dt = datetime.fromisoformat(to_date).date()
        assert to_dt >= from_dt

        assert request.url.params["adjusted"].lower() == "true"
        assert request.url.params["sort"] == "desc"
        assert request.url.params["limit"] == "108"

        payload_count = 2 if call_count == 1 else 120
        data = {"results": results[:payload_count]}
        return httpx.Response(200, json=data)

    transport = httpx.MockTransport(handler)

    client = MassiveClient(api_key="test", timeout=1.0)
    client.base_url = "https://example.com"
    client.client = httpx.Client(transport=transport, headers=client.client.headers)

    bars = client.get_bars("SPY", "5m", 36)

    assert isinstance(bars, list)
    assert len(bars) == 36
    assert call_count == 2
    assert len(from_dates) == 2
    assert datetime.fromisoformat(from_dates[1]).date() < datetime.fromisoformat(from_dates[0]).date()


def test_get_bars_uses_multiday_range_for_large_limits(monkeypatch):
    fixed_now = datetime(2026, 1, 5, 12, 0, tzinfo=ZoneInfo("America/New_York"))
    _set_fixed_datetime(monkeypatch, fixed_now)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.startswith("/v2/aggs/ticker/SPY/range/5/minute/")
        parts = request.url.path.rstrip("/").split("/")
        from_date = parts[-2]
        to_date = parts[-1]
        from_dt = datetime.fromisoformat(from_date).date()
        to_dt = datetime.fromisoformat(to_date).date()
        assert to_dt > from_dt
        assert (to_dt - from_dt).days >= 3
        return httpx.Response(200, json={"results": [{"t": i} for i in range(700)]})

    transport = httpx.MockTransport(handler)
    client = MassiveClient(api_key="test", timeout=1.0)
    client.base_url = "https://example.com"
    client.client = httpx.Client(transport=transport, headers=client.client.headers)

    bars = client.get_bars("SPY", "5m", 600)

    assert len(bars) == 600


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

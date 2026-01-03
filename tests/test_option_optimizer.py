from datetime import datetime

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.strategies.option_optimizer import OptionOptimizer


def mock_chain(exp):
    return [
        {"symbol": f"TEST-{exp}-C1", "strike": 100, "bid": 1.0, "ask": 1.06, "volume": 500, "oi": 600, "delta": 0.55, "gamma": 0.1, "theta": -0.05, "iv": 0.4, "type": "C"},
        {"symbol": f"TEST-{exp}-C2", "strike": 102, "bid": 0.6, "ask": 0.64, "volume": 400, "oi": 700, "delta": 0.4, "gamma": 0.12, "theta": -0.03, "iv": 0.42, "type": "C"},
        {"symbol": f"TEST-{exp}-C3", "strike": 103, "bid": 0.3, "ask": 0.32, "volume": 300, "oi": 800, "delta": 0.3, "gamma": 0.15, "theta": -0.02, "iv": 0.45, "type": "C"},
    ]


def test_optimizer_returns_three_candidates():
    opt = OptionOptimizer()
    expirations = ["2024-01-05", "2024-01-10"]
    now = datetime(2024, 1, 2, 13, 0)
    result = opt.run("TEST", "LONG", "same_day", now, expirations, mock_chain, iv_percentile=0.2)
    assert not result.stock_only
    assert len(result.candidates) == 3
    tiers = {c.tier for c in result.candidates}
    assert "Conservative" in tiers and "Standard" in tiers and any(c.tier.startswith("Aggressive") or c.tier == "Aggressive" for c in result.candidates)

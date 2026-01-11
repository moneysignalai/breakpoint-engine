from __future__ import annotations

import json

from src.services.massive_client import MassiveClient


def main() -> None:
    client = MassiveClient()
    try:
        health = client.health_check("SPY")
        bars = client.get_bars("SPY", timeframe="5m", limit=36)
    finally:
        client.close()

    print(f"health_ok={health.get('ok') if isinstance(health, dict) else health}")
    print(f"health_details={health}")
    print(f"len(spy_bars)={len(bars)}")
    preview = bars[:2]
    print(json.dumps(preview, default=str, indent=2))


if __name__ == "__main__":
    main()

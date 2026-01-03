# Breakpoint Engine

A single flagship strategy implementation: **Compression → Expansion Breakout (Stock-led, Options-optimized)**. Runs a FastAPI web service with a Render worker that scans equities, logs results to Postgres, and produces actionable stock + options alerts with deterministic scoring.

## Strategy Overview
- Timeframe: 5m bars, compression box of 12 bars.
- Filters: price/volume sanity, ATR compression, volume contraction, tight range, box integrity, and market bias gate (VWAP + trend, chop/panic detection).
- Trigger: close beyond box with volume and extension guards; VWAP confirmation optional.
- Trade idea: buffered entry/stop, R-multiples for T1/T2, expected window based on time of day.
- Confidence: base 7.0 plus deterministic adds for market alignment, breakout quality, candle position; capped and penalized for weak options liquidity.
- Options: optimizer selects three tiers (Conservative/Standard/Aggressive) honoring spreads, volume/OI, delta bands, IV thresholds, and expiry windows.

## Required Environment Variables
See `src/config.py` for defaults.
- `MASSIVE_API_KEY`
- `DATABASE_URL`
- `TELEGRAM_ENABLED` (default false)
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `SCAN_INTERVAL_SECONDS` (default 60)
- `UNIVERSE` (comma tickers; default includes SPY/QQQ/IWM and megacaps)
- `RTH_ONLY` (default true)
- `MIN_CONFIDENCE_TO_ALERT` (default 7.5)
- `TIMEZONE` (default America/New_York)
- Optional tuning knobs: pricing/volume thresholds, box/ATR/volume factors, breakout buffers, VWAP confirm, option liquidity and IV guards, allowed windows.

## Local Development
```bash
pip install -r requirements.txt  # ensure FastAPI, SQLAlchemy, httpx, loguru, pydantic-settings, pytz, numpy, pandas, pytest
export MASSIVE_API_KEY=demo
export DATABASE_URL=sqlite:///./local.db
uvicorn src.main:app --reload
```
Run worker loop once manually:
```bash
python -m src.worker
```
Run tests:
```bash
pytest
```

## Render Deployment
- **Web Service**: `uvicorn src.main:app --host 0.0.0.0 --port $PORT`
- **Background Worker**: `python -m src.worker`
- **Postgres**: Render managed; set `DATABASE_URL` accordingly.
- Provide env vars in both service and worker. TELEGRAM_* optional; TELEGRAM_ENABLED defaults to false.

## API Endpoints
- `GET /health` – basic status
- `GET /config` – non-secret runtime config
- `POST /run-scan` – one-shot scan (debug/manual)
- `GET /latest-alerts?limit=20` – latest alerts with option candidates

## Example Output
`POST /run-scan` returns JSON such as:
```json
{"alerts": [{"symbol": "NVDA", "direction": "LONG", "confidence": 8.0}], "notes": []}
```

Deep dive alert sample:
```
NVDA LONG compression breakout
Box: 450.00-454.50 (range 1.00%)
Trigger close beyond box: 0.15% beyond edge
Breakout volume: 1.60x box avg
ATR compression ratio: 0.70
VWAP confirmation: True
Market bias: LONG
Plan: entry 454.70 stop 453.80 T1 455.60 T2 456.50 (conf 8.0)
Conservative: NVDA 2024-01-12 455C mid 2.50 sprd 4.0% vol 1200 oi 3200 delta 0.55
Standard: NVDA 2024-01-12 460C mid 1.70 sprd 5.0% vol 900 oi 2800 delta 0.40
Aggressive: NVDA 2024-01-12 465C mid 1.10 sprd 6.0% vol 700 oi 2000 delta 0.30
Exit: Take 40-60% at T1, runner to T2, time stop 30-60m if no continuation, exit on invalidation
```

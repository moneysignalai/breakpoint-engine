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

Standard alert sample:
```
🔥 BREAKPOINT TRIGGER — NVDA

SETUP
• Tight compression box resolved with expansion
• Range: 1.05% (last 12 × 5m bars)
• Breakout close: +0.20% beyond box
• Volume: 1.60× box average
• VWAP: Confirmed
• Market bias: Bullish

STOCK PLAN
• Entry: 454.70 (hold above)
• Invalidation: 453.80 (back inside box)
• Target 1: 455.60
• Target 2: 456.50
• Expected window: Same day → 1–3 days

OPTIONS (LIQUID / WEEKLY)
• Conservative: 455C (5 DTE | Δ 0.55 | Mid 2.50 | Sprd 4.00%)
• Standard:     460C (5 DTE | Δ 0.40 | Mid 1.70 | Sprd 5.00%)
• Aggressive:   465C (5 DTE | Δ 0.30 | Mid 1.10 | Sprd 6.00%)

RISK NOTES
• Take 40–60% at T1
• Runner to T2
• Time stop: exit if no continuation in 30–60 min
• Exit on invalidation (back inside box)

Confidence: 8.0 / 10
```

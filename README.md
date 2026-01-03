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
pip install -r requirements.txt
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

## Deploy on Render
Deploy either by importing the included Render Blueprint or by creating services manually.

### Option A: Blueprint (recommended)
1. Push this repository to your own GitHub account.
2. In Render, choose **Blueprints → New Blueprint Instance** and point to `render.yaml` in this repo.
3. Confirm the defaults:
   - **Web service build**: `pip install -r requirements.txt`
   - **Web service start**: `bash -lc "alembic upgrade head && uvicorn src.main:app --host 0.0.0.0 --port $PORT"`
   - **Worker start**: `bash -lc "alembic upgrade head && python -m src.worker"`
4. Add required secrets when prompted (see env vars below) and launch.

### Option B: Manual services
1. Create a **Postgres** instance (e.g., `breakpoint-db`) and note the `DATABASE_URL`.
2. Create a **Web Service** from this repo with:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `bash -lc "alembic upgrade head && uvicorn src.main:app --host 0.0.0.0 --port $PORT"`
   - Health Check Path: `/health`
3. Create a **Background Worker** from this repo with:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `bash -lc "alembic upgrade head && python -m src.worker"`
4. Set identical environment variables on both services. Connect `DATABASE_URL` to the Render Postgres instance.

### Environment variables
Set on both the web service and worker (defaults come from `src/config.py`):

- `MASSIVE_API_KEY` *(required)*
- `DATABASE_URL` *(required; provided by Render Postgres connection string)*
- `TELEGRAM_ENABLED` (default `false`)
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `TIMEZONE` (default `America/New_York`)
- `RTH_ONLY` (default `true`)
- `SCAN_INTERVAL_SECONDS` (default `60`)
- `MIN_CONFIDENCE_TO_ALERT` (default `7.5`)
- `UNIVERSE` (default `SPY,QQQ,IWM,NVDA,TSLA,AAPL,MSFT,AMZN,META,AMD,AVGO`)

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

# Breakpoint Engine — deterministic market alerts with built-in guardrails

Breakpoint Engine is a production-grade scanner and alert builder for high-quality stock and options setups. It keeps alerts scarce, structured, and explainable for operators while communicating value to capital allocators who care about discipline.

## Executive Overview
- Focused on one flagship structural breakout setup; no strategy sprawl.
- Deterministic gating and scoring to avoid alert spam.
- Options tiers only when liquidity, spread, and IV thresholds are met.
- Production delivery via FastAPI + PostgreSQL + Telegram with audit trails.
- Built for operators who need clarity and for investors who need rigor.

## What It Does
- Scans a defined equity universe on a schedule and filters by liquidity, price, and volatility constraints.
- Evaluates a boxed-range breakout pattern with volume and ATR compression checks.
- Scores every candidate; suppresses anything below the minimum confidence threshold.
- Produces structured alerts with setup rationale, trade plan, and optional options ladders.
- Persists alerts and option candidates for review, analytics, and future strategy work.

## Why It’s Different
- **Deterministic core**: one setup with explicit thresholds—no discretionary “vibes.”
- **Scoring + gating**: alerts are suppressed unless minimum confidence is met.
- **Explainable output**: every alert includes why it fired, risk notes, and confidence.
- **Anti-spam design**: liquidity, spread, IV, and session windows prevent junk signals.
- **Production-ready**: worker loop, API layer, migrations, and Render deployment baked in.

## Alert Output (Exact Format)
The examples below mirror the generator in `src/services/alerts.py`. Section headers, emojis, ordering, and wording are unchanged.

### STANDARD
```
─────────────────
⚡ BREAKPOINT ALERT - NVDA
🕒 05-06-2024 10:42 AM ET  
⏰ ⏱ RTH · 🚦 Bias: Bullish

🧠 SETUP
• Box Range: 0.80% (12×5m) · Break: 0.45% · Vol: 2.40×
• VWAP: Confirmed · Trend: Uptrend

📈 STOCK PLAN
• Entry: 915.20 (hold above)
• Invalidation: 902.80 (back inside box)
• Targets: 930.00 → 945.00
• Window: 1–3 days

🎯 OPTIONS (Weekly / Liquid)
• 🟢 Conservative:   910C
(5 DTE | Δ 0.42 | Mid 3.10 | Sprd 1.50%)
• 🟡 Standard:       920C
(5 DTE | Δ 0.31 | Mid 1.85 | Sprd 1.75%)
• 🔴 Aggressive:     930C
(5 DTE | Δ 0.22 | Mid 1.05 | Sprd 2.00%)

🛡️ RISK NOTES
• Take 40–60% at T1 · Runner to T2
• Time stop: 30–60 min if no continuation
• Hard exit if invalidation triggers

⭐ Confidence: 7.2 / 10
─────────────────
```

### STOCK-ONLY OPTIONS BEHAVIOR
(Options header stays; the options line indicates no qualified contracts.)
```
🎯 OPTIONS (Weekly / Liquid)
• stock-only (no liquid contracts / IV too high / unavailable)
```

### SHORT
```
SPY LONG entry 525.25 stop 519.50 T1 533.00 T2 540.00 (conf 7.8)
```

### DEEP
```
SPY LONG compression breakout
Box: 518.00-522.00 (range 0.76%)
Trigger close beyond box: 0.35% beyond edge
Breakout volume: 2.40x box avg
ATR compression ratio: 1.20
VWAP confirmation: True
Market bias: Bullish
Plan: entry 525.25 stop 519.50 T1 533.00 T2 540.00 (conf 7.8)
Conservative: SPY240621C520 mid 6.95 sprd 2.9% vol 1123 oi 20450 delta 0.45
Standard: SPY240621C525 mid 4.45 sprd 4.5% vol 8420 oi 35670 delta 0.38
Aggressive: SPY240621C530 mid 2.45 sprd 8.2% vol 15320 oi 41200 delta 0.31
Exit: Take 40-60% at T1, runner to T2, time stop 30-60m if no continuation, exit on invalidation
```

## System Architecture
```mermaid
flowchart LR
  A[Market Data Provider] --> B[Worker Scanner]
  B --> C[Flagship Strategy + Gating]
  C -->|Meets thresholds| D[Options Optimizer]
  D --> E[Alert Builder]
  E --> F[(PostgreSQL)]
  E --> G[Telegram Delivery]
  F --> H[FastAPI for review / ops]
  H --> I[Operators & Monitoring]
```

## Quality Controls (Why Alerts Aren’t Spam)
- Minimum confidence enforced (`MIN_CONFIDENCE_TO_ALERT`).
- Liquidity, spread, and IV caps before options are allowed.
- Session-aware gating (`RTH_ONLY`, `ALLOWED_WINDOWS`) plus optional outside-window override.
- Box range, ATR compression, and breakout volume thresholds prevent marginal setups.
- Options optimizer downgrades confidence when only stock is viable.
- Alerts persist with metadata for auditability.

## Quickstart (Local)
### Environment
Create a `.env` with at least:
```
MASSIVE_API_KEY=your_api_key
DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/db
TELEGRAM_ENABLED=false
TELEGRAM_BOT_TOKEN=optional_bot_token
TELEGRAM_CHAT_ID=optional_chat_id
UNIVERSE=SPY,QQQ,IWM,NVDA,TSLA,AAPL,MSFT,AMZN,META,AMD,AVGO
TIMEZONE=America/New_York
RTH_ONLY=true
SCAN_INTERVAL_SECONDS=60
MIN_CONFIDENCE_TO_ALERT=7.5
```

### Install, migrate, and run
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=.
alembic upgrade head
# Start the API (health, config, manual scan endpoints)
uvicorn src.main:app --host 0.0.0.0 --port 8000
# Start the worker scanner (in another shell)
python -m src.worker
```

## Deployment (Render)
- `render.yaml` defines a **web** service (`uvicorn src.main:app`) and a **worker** service (`python -m src.worker`).
- Both services run migrations on boot: `alembic upgrade head`.
- PostgreSQL is provisioned as `breakpoint-db`; `DATABASE_URL` is injected from the Render database connection string.
- Env vars such as `MASSIVE_API_KEY`, `TELEGRAM_*`, `TIMEZONE`, `RTH_ONLY`, `SCAN_INTERVAL_SECONDS`, `MIN_CONFIDENCE_TO_ALERT`, and `UNIVERSE` map directly to `src/config.py`.

## Configuration
All settings are defined in `src/config.py` (Pydantic). Key variables:
- `MASSIVE_API_KEY` – credentials for the market data provider (required).
- `MASSIVE_BARS_PATH_TEMPLATE` – override for the Massive bars endpoint path template (default `/markets/{symbol}/bars`).
- `DATABASE_URL` – SQLAlchemy connection string (required).
- `TELEGRAM_ENABLED`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` – delivery controls.
- `SCAN_INTERVAL_SECONDS` – worker cadence.
- `UNIVERSE` – comma-separated symbols scanned each cycle.
- `RTH_ONLY`, `SCAN_OUTSIDE_WINDOW`, `ALLOWED_WINDOWS`, `TIMEZONE` – session controls.
- `MIN_CONFIDENCE_TO_ALERT` – gating threshold for sending alerts.
- `MIN_AVG_DAILY_VOLUME`, `MIN_PRICE`, `MAX_PRICE` – base liquidity and price filters.
- `BOX_BARS`, `BOX_MAX_RANGE_PCT`, `ATR_COMP_FACTOR`, `VOL_CONTRACTION_FACTOR`, `BREAK_BUFFER_PCT`, `MAX_EXTENSION_PCT`, `BREAK_VOL_MULT`, `VWAP_CONFIRM` – flagship setup parameters.
- `SPREAD_PCT_MAX`, `MIN_OPT_VOLUME`, `MIN_OPT_OI`, `MIN_OPT_MID`, `IV_PCTL_MAX_FOR_AGG`, `IV_PCTL_MAX_FOR_ANY` – options eligibility thresholds.
- `ENTRY_BUFFER_PCT`, `STOP_BUFFER_PCT` – execution buffers for entries and stops.

## Operational Logging
- **scan start** – includes the universe size and session window label (RTH/PM/AH) so you know the worker cadence and gating state.
- **scan end** – always reports duration, symbols scanned, alerts triggered, and errors plus a reason (e.g., `outside_window`, `api_error`). When `scanned=0`, a warning is emitted to highlight anomalies.
- **scan symbol error** – single-line summaries per symbol with stage (`bars`, `options_expirations`, `alert_send`, etc.) and the status/exception reason to quickly isolate failing calls.
- **alert send result** – reports Telegram delivery outcome with status and reason while omitting secrets.
- A dedicated warning surfaces if the Massive bars endpoint returns multiple 404s in a scan to hint at route/template misconfiguration.

## Repo Layout
```
README.md
render.yaml
requirements.txt
runtime.txt
alembic.ini
alembic/
  versions/        # database migrations
src/
  main.py          # FastAPI entrypoint
  worker.py        # scheduled scanner + alert publisher
  config.py        # environment-backed settings
  services/
    alerts.py      # alert formatting & Telegram sender
    db.py          # session management + init
    market_time.py # session gating helpers
  models/          # SQLAlchemy models (Alert, OptionCandidate, etc.)
  strategies/      # flagship strategy + option optimizer
  utils/           # logging and helpers
tests/
```

## Roadmap
- Post-alert analytics (MFE/MAE, time-to-peak, stop-out timing).
- Operator dashboard for latest alerts and audit trails.
- Additional delivery channels (webhooks, Slack) with the same format discipline.
- Configurable universes per deployment without changing code.

## Compliance / Reality Check
- Provides market intelligence and structured alerts, not financial advice.
- No profit guarantees or certainty of outcomes.
- Users remain responsible for execution, risk limits, and compliance obligations.

## About / Contact
Built and maintained by the Breakpoint team. For collaboration or deployment inquiries, open an issue in this repository.

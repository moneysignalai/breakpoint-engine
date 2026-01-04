# Breakpoint Engine

Real-time, disciplined stock + options alerts built for professional-grade transparency and control.

## Executive Overview
Breakpoint Engine is an intelligent alert engine that watches liquid equities intraday and emits structured plans when a single flagship compression-breakout setup aligns. It is not a signals chat. Every alert is deterministic: score the setup, gate on confidence, format the plan, and send.

- **Audience:** technical evaluators who need rigor, and active investors who demand clarity over hype.
- **What you get:** pre-scored alerts with stock and options context, risk notes, and confidence—no guesswork, no spam.

## What Breakpoint Engine Does
- Continuously scans a configurable universe for a compression-to-expansion breakout pattern.
- Applies liquidity, spread, volatility, and VWAP guardrails before any alert can fire.
- Scores each candidate and only emits when confidence clears the configured threshold.
- Packages the stock plan and liquid weekly options (when available) into a deterministic alert format.
- Delivers via Telegram with Markdown-safe formatting; also queryable through the FastAPI service.

## Why It’s Different
- **One flagship setup:** No strategy sprawl. Depth over breadth allows tighter controls and explainability.
- **Signal gating:** Alerts must clear minimum confidence, time-window rules, and liquidity/spread filters.
- **Structured outputs:** Every alert follows the exact same template, including risk notes and confidence score.
- **Deterministic scoring:** Inputs and thresholds are explicit in `src/config.py`, enabling reproducibility and audits.

## Alert Output (Exact Format)
The alert format below mirrors `build_alert_texts()` in `src/services/alerts.py`.

### STANDARD alert example
```
─────────────────
⚡ BREAKPOINT ALERT - NVDA
🕒 05-06-2024 10:42 AM ET  
⏰ ⏱ RTH · 🚦 Bias: Bullish

🧠 SETUP
• Box Range: 0.86% (12×5m) · Break: 0.35% · Vol: 2.35×
• VWAP: Confirmed · Trend: Uptrend

📈 STOCK PLAN
• Entry: 873.25 (hold above)
• Invalidation: 864.80 (back inside box)
• Targets: 888.50 → 905.20
• Window: Same day → 1–3 days

🎯 OPTIONS (Weekly / Liquid)
• 🟢 Conservative: 875C
(6 DTE | Δ 0.35 | Mid 3.23 | Sprd 7.75%)
• 🟡 Standard:     885C
(6 DTE | Δ 0.28 | Mid 2.23 | Sprd 11.24%)
• 🔴 Aggressive:   900C
(6 DTE | Δ 0.18 | Mid 1.15 | Sprd 17.39%)

🛡️ RISK NOTES
• Take 40–60% at T1 · Runner to T2
• Time stop: 30–60 min if no continuation
• Hard exit if invalidation triggers

⭐ Confidence: 7.2 / 10
─────────────────
```

### SHORT alert example
```
NVDA LONG entry 873.25 stop 864.80 T1 888.50 T2 905.20 (conf 7.2)
```

### DEEP alert example
```
NVDA LONG compression breakout
Box: 864.80-873.25 (range 0.86%)
Trigger close beyond box: 0.35% beyond edge
Breakout volume: 2.35x box avg
ATR compression ratio: 0.75
VWAP confirmation: True
Market bias: Bullish
Plan: entry 873.25 stop 864.80 T1 888.50 T2 905.20 (conf 7.2)
Aggressive: NVDA240510C00900000 mid 1.15 sprd 17.4% vol 2300 oi 5100 delta 0.18
Exit: Take 40-60% at T1, runner to T2, time stop 30-60m if no continuation, exit on invalidation
```

When options liquidity fails the guardrails, the options block is replaced with `• stock-only (no liquid contracts / IV too high / unavailable)`.

## System Architecture
```mermaid
graph TD
    A[Massive market data API] --> B[Worker (compression scanner)]
    B --> C[Scoring & gating logic]
    C --> D[PostgreSQL]
    C --> E[Telegram delivery]
    D --> F[FastAPI service]
    F --> |/health, alerts| G[Operators / dashboards]
```

## Quickstart (Local)
1. **Install dependencies**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. **Set environment** (create `.env` or export variables):
   ```bash
   export MASSIVE_API_KEY=your_key
   export DATABASE_URL=postgresql://user:pass@localhost:5432/breakpoint
   export TELEGRAM_ENABLED=false  # set true only when credentials are present
   # optional overrides: SCAN_INTERVAL_SECONDS, UNIVERSE, MIN_CONFIDENCE_TO_ALERT, TIMEZONE, RTH_ONLY
   ```
3. **Run migrations**
   ```bash
   alembic upgrade head
   ```
4. **Start services**
   - Web API: `export PYTHONPATH=. && uvicorn src.main:app --host 0.0.0.0 --port 8000`
   - Worker:  `export PYTHONPATH=. && python -m src.worker`

## Deployment (Render)
- Defined in `render.yaml` with a shared PostgreSQL database (`breakpoint-db`).
- **Web service** start command: `bash -lc "export PYTHONPATH=. && alembic upgrade head && uvicorn src.main:app --host 0.0.0.0 --port $PORT"`
- **Worker service** start command: `bash -lc "export PYTHONPATH=. && alembic upgrade head && python -m src.worker"`
- Default env vars include `TIMEZONE=America/New_York`, `SCAN_INTERVAL_SECONDS=60`, `RTH_ONLY=true`, and `MIN_CONFIDENCE_TO_ALERT=7.5`.

## Configuration
Key tunables from `src/config.py` (override via env vars):
- **MASSIVE_API_KEY**: market data access.
- **DATABASE_URL**: PostgreSQL connection string.
- **TELEGRAM_ENABLED / TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID**: messaging control and credentials.
- **SCAN_INTERVAL_SECONDS**: worker scan cadence.
- **UNIVERSE**: comma-separated symbols to monitor.
- **RTH_ONLY / SCAN_OUTSIDE_WINDOW / ALLOWED_WINDOWS**: trading-hour gating.
- **MIN_CONFIDENCE_TO_ALERT**: minimum score to emit alerts.
- **Liquidity + structure guards:** `MIN_AVG_DAILY_VOLUME`, `MIN_PRICE`, `MAX_PRICE`, `BOX_BARS`, `BOX_MAX_RANGE_PCT`, `ATR_COMP_FACTOR`, `VOL_CONTRACTION_FACTOR`, `BREAK_BUFFER_PCT`, `MAX_EXTENSION_PCT`, `BREAK_VOL_MULT`, `VWAP_CONFIRM`.
- **Options filters:** `SPREAD_PCT_MAX`, `MIN_OPT_VOLUME`, `MIN_OPT_OI`, `MIN_OPT_MID`, `IV_PCTL_MAX_FOR_AGG`, `IV_PCTL_MAX_FOR_ANY`, `ENTRY_BUFFER_PCT`, `STOP_BUFFER_PCT`.

## Quality Controls / Why Alerts Aren’t Spam
- **Confidence gating:** alerts must exceed `MIN_CONFIDENCE_TO_ALERT` and respect allowed windows.
- **Liquidity checks:** minimum average daily volume and price ranges enforced before scoring.
- **Compression discipline:** box size, ATR compression, and volatility contraction thresholds gate entries.
- **VWAP + bias confirmation:** directional bias and VWAP confirmation are required for standard alerts.
- **Options liquidity guardrails:** spread, volume, open interest, and IV percentile filters decide whether options tiers appear or if the alert is stock-only.
- **Transparent plans:** every alert includes entry, invalidation, targets, risk notes, and a confidence score for auditability.

## Repo Layout
- `src/main.py` – FastAPI entrypoint exposing health, config, and latest alerts.
- `src/worker.py` – scheduler loop that scans, scores, and writes alerts.
- `src/services/` – alert formatting, market-time gating, database helpers, grading, Massive API client.
- `src/strategies/` – flagship logic and option optimizer.
- `src/models/` – SQLAlchemy models for alerts, option candidates, grades, and scan runs.
- `alembic/` & `alembic.ini` – migrations and migration config.
- `tests/` – unit tests for flagship logic and option optimizer.
- `render.yaml` – Render web + worker service definitions.

## Roadmap
- Live dashboards for scan history, scores, and alert telemetry.
- Expanded analytics on post-alert outcomes and adherence to plans.
- Additional delivery channels (e.g., webhooks) while keeping the single flagship setup.
- Hardening around retry logic and observability for both worker and API.

## Compliance / Reality Check
Breakpoint Engine provides structured market intelligence, not financial advice. No profits are promised or implied. Trading involves risk, including potential loss of principal. Users control execution, sizing, and risk decisions; use these alerts as disciplined context, not directives.

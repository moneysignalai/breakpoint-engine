# Breakpoint Engine

## Executive Overview (Investor-Friendly)
Breakpoint Engine is an alert intelligence system that monitors liquid equities intraday and surfaces high-conviction moments where price, volume, and market context align. It exists to remove guesswork and emotion from short-term trading by applying the same rules on every scan. Traders keep control of execution; the engine supplies disciplined, repeatable alerts that emphasize risk awareness over impulse.

Modern discretionary trading often suffers from inconsistent decision-making. Breakpoint Engine addresses this by enforcing automation and pre-defined criteria, ensuring that alerts are generated only when a structured checklist is satisfied. Automation plus discipline reduces emotional drift, creates auditability, and scales without diluting the quality of insights. The system delivers timely, actionable context rather than promising profits or selling signals.

--------------------------------------------------
## What Makes Breakpoint Engine Different
- **One flagship setup**: The engine centers on a single compression-to-expansion breakout framework. Focusing on one setup enables deep guardrails, consistent evaluation, and clear expectations instead of a patchwork of loosely tested ideas.
- **Avoiding strategy sprawl**: Many bots juggle too many half-finished strategies and produce noisy pings. Breakpoint only scans for high-conviction market moments that meet strict structure, liquidity, and volatility requirements.
- **Actionable, not spammy**: Alerts are throttled by deterministic scoring and minimum confidence gates. Each alert contains the reasoning and risk notes needed for a trader to act—or pass—with clarity.

--------------------------------------------------
## System Architecture (Technical Overview)
Breakpoint Engine is implemented in Python 3.11 for stability and modern typing support. The system is split into a stateless FastAPI web service and a background worker that runs the scanning and evaluation loop. Persistence is handled by PostgreSQL with Alembic migrations to keep schemas consistent. Alerts are delivered via Telegram, and the full stack is deployable on Render.

```
                +---------------------+
                |   Telegram Client   |
                +----------+----------+
                           ^
                           |
+-----------+      +-------+--------+      +----------------+
| Massive   | ---> | Background     | ---> | PostgreSQL     |
| Market API|      | Worker (scan)  |      | (alerts, runs) |
+-----------+      +-------+--------+      +----------------+
                           |
                           v
                  +--------+-------+
                  | FastAPI Web    |
                  | Service        |
                  +--------+-------+
                           |
                           v
                       Render Cloud
```

Key characteristics:
- **FastAPI web service** (`src/main.py`) exposes health, config, latest alerts, and a manual scan trigger.
- **Background worker** (`src/worker.py`) runs the flagship strategy on a schedule; evaluation logic is deterministic and stateless between scans, drawing fresh data each cycle.
- **PostgreSQL + Alembic** store alerts, option candidates, and scan metadata with controlled migrations.
- **Telegram delivery** is optional and controlled via environment flags, ensuring safe defaults when disabled.
- **Render deployment** uses separate web and worker services defined in `render.yaml` with health checks and shared environment configuration.

--------------------------------------------------
## Flagship Strategy Philosophy (No Trade Secrets)
Breakpoint Engine evaluates the underlying stock first. It looks for periods where liquidity, volatility compression, and directional momentum align, signaling potential breakouts. Options are treated as derivatives of the stock thesis: contracts are only considered when the stock setup is valid and when liquidity and spreads meet guardrails.

The system can emit stock-only alerts when options liquidity is insufficient, option-focused context when contracts are viable, or combined alerts when both align. Proprietary thresholds and formulas remain internal, but the flow is consistent: validate the stock structure → confirm volume and market bias → evaluate extension risk →, if qualified, select options that mirror the stock thesis.

--------------------------------------------------
## Alert Types
- **Stock alerts**: Triggered when the stock meets the flagship setup with adequate confidence. Suitable for traders who prefer equity exposure or who want to handle derivatives themselves.
- **Options alerts**: Generated when the stock qualifies and options liquidity/spread criteria are met. Includes contract context without forcing execution.
- **Combined alerts**: Provide both stock structure and vetted option candidates so traders can choose the instrument that fits their risk tolerance.

Traders may take the stock only, use the stock signal to select their own contracts, or reference the provided option context as guidance. Execution choices remain with the user.

--------------------------------------------------
## Alert Format (STANDARD TEMPLATE)
A typical Telegram alert follows this structure:

⚡ BREAKPOINT ALERT — TICKER  
📊 Direction: Bullish  
🧠 Setup: Breakpoint Momentum  
⏱ Timeframe: Intraday / Short-term  

📈 STOCK CONTEXT  
• Price: $XXX.XX  
• VWAP: Above  
• Trend: Higher Lows  
• Volume: Elevated vs baseline  

🎯 OPTIONS CONTEXT (If Applicable)  
• Contract: 100C  
• Expiration: 2024-12-20  
• Liquidity: Sufficient  
• Premium Range: $1.10 – $1.30  

🧭 RISK NOTES  
• Not a market order  
• Wait for confirmation  
• Manage position size  

⚠️ Alerts are informational, not financial advice.

--------------------------------------------------
## Risk & Compliance Disclosure
Breakpoint Engine issues informational alerts only. They are not trading advice or execution instructions. Markets carry risk, and users are responsible for their own orders, position sizing, and outcomes. The system does not automate trades or guarantee performance. Past alerts do not predict future results.

--------------------------------------------------
## Deployment & Reliability
- **Render cloud deployment** with separate web and worker services, each built from the same codebase and sharing environment variables.
- **Health checks** on the FastAPI service for uptime monitoring.
- **Environment control** via configuration flags for scan intervals, trading hours gating, and enabling/disabling Telegram.
- **Safety defaults** keep Telegram disabled unless credentials are provided.
- **Database-backed logging** records every alert and scan run for auditability and post-trade review.

--------------------------------------------------
## Who This Is For
- Active traders who want structured, repeatable intraday setups.
- Options traders who anchor decisions to the underlying stock first.
- Stock-first traders who occasionally layer options when liquidity permits.
- Practitioners who value discipline and clarity over hype and opaque promises.

--------------------------------------------------
## Roadmap (High-Level, Honest)
- Additional alert types that extend the flagship philosophy without diluting quality.
- Expanded analytics for post-alert outcomes and behavior tracking.
- UI dashboards for monitoring scans, alert history, and configuration.
- Performance review tooling to evaluate adherence to plans and risk controls.

--------------------------------------------------
## Closing Statement
Breakpoint Engine is built on discipline, transparency, and a focused playbook. By enforcing structure and surfacing only the most compelling setups, it helps traders operate with clarity and repeatability. The long-term vision is a resilient alert infrastructure that scales while keeping risk-awareness at its core.

from __future__ import annotations

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List

from loguru import logger

from src.config import get_settings
from src.models.alert import Alert
from src.models.option_candidate import OptionCandidate
from src.models.scan_run import ScanRun
from src.services import alerts as alert_service
from src.services.db import session_scope, init_db
from src.services.market_time import in_allowed_window, is_rth
from src.services.massive_client import MassiveClient
from src.strategies.flagship import FlagshipStrategy
from src.strategies.option_optimizer import OptionOptimizer, OptionPick

settings = get_settings()


def run_scan_once(client: MassiveClient | None = None) -> Dict[str, Any]:
    client = client or MassiveClient()
    strategy = FlagshipStrategy()
    optimizer = OptionOptimizer()

    started_at = datetime.utcnow()
    scan_notes = []
    errors = 0
    alerts_triggered: List[Dict[str, Any]] = []

    with session_scope() as session:
        scan_run = ScanRun(started_at=started_at, finished_at=None, universe=settings.UNIVERSE, symbols_scanned=[])
        session.add(scan_run)
        session.flush()

        if settings.RTH_ONLY and not is_rth():
            scan_run.finished_at = datetime.utcnow()
            scan_run.notes = "Outside RTH"
            return {"alerts": [], "notes": "Outside RTH"}

        market_symbol = "QQQ"
        market_bars = client.get_bars(market_symbol, timeframe="5m", limit=settings.BOX_BARS * 3)

        for symbol in settings.universe_list():
            try:
                bars = client.get_bars(symbol, timeframe="5m", limit=settings.BOX_BARS * 3)
                daily = client.get_daily_snapshot(symbol)
                idea = strategy.evaluate(symbol, bars, daily, market_bars)
                if not idea:
                    continue

                expirations = client.get_option_expirations(symbol)
                iv_pct = daily.get('iv_percentile') if isinstance(daily, dict) else None

                def load_chain(exp: str):
                    return client.get_option_chain(symbol, exp)

                opt_result = optimizer.run(symbol, idea.direction, idea.expected_window, bars[-1]['ts'] if isinstance(bars[-1]['ts'], datetime) else datetime.fromisoformat(bars[-1]['ts']), expirations, load_chain, iv_percentile=iv_pct)

                confidence = idea.confidence
                option_picks: List[OptionPick] = []
                if opt_result.stock_only:
                    confidence = max(0.0, confidence - 1.0)
                    idea.debug['debug_reasons'].append(opt_result.reason or "stock-only")
                else:
                    option_picks = opt_result.candidates

                if confidence < settings.MIN_CONFIDENCE_TO_ALERT:
                    continue

                alert_dict = {
                    "symbol": symbol,
                    "direction": idea.direction,
                    "confidence": confidence,
                    "expected_window": idea.expected_window,
                    "entry": idea.entry,
                    "stop": idea.stop,
                    "t1": idea.t1,
                    "t2": idea.t2,
                    "box_high": idea.debug['box_high'],
                    "box_low": idea.debug['box_low'],
                    "range_pct": idea.debug['range_pct'],
                    "atr_ratio": idea.debug['atr_ratio'],
                    "vol_ratio": idea.debug['vol_ratio'],
                    "break_vol_mult": idea.debug['break_vol_mult'],
                    "extension_pct": idea.debug['extension_pct'],
                    "market_bias": idea.debug.get('market_bias'),
                    "vwap_ok": idea.debug['vwap_ok'],
                }
                option_payloads = []
                if option_picks:
                    for pick in option_picks:
                        option_payloads.append({
                            "tier": pick.tier,
                            "contract_symbol": pick.contract.contract_symbol,
                            "expiry": pick.contract.expiry,
                            "strike": pick.contract.strike,
                            "call_put": pick.contract.call_put,
                            "bid": pick.contract.bid,
                            "ask": pick.contract.ask,
                            "mid": pick.contract.mid,
                            "spread_pct": pick.contract.spread_pct,
                            "volume": pick.contract.volume,
                            "oi": pick.contract.oi,
                            "delta": pick.contract.delta,
                            "gamma": pick.contract.gamma,
                            "theta": pick.contract.theta,
                            "iv": pick.contract.iv,
                            "iv_percentile": pick.contract.iv_percentile,
                            "rationale": pick.rationale,
                            "exit_plan": pick.exit_plan,
                        })

                texts = alert_service.build_alert_texts(alert_dict, option_payloads if option_payloads else None)
                status_code, tg_resp = alert_service.send_telegram_message(texts['short'])

                alert_row = Alert(
                    symbol=symbol,
                    direction=idea.direction,
                    confidence=confidence,
                    expected_window=idea.expected_window,
                    entry=idea.entry,
                    stop=idea.stop,
                    t1=idea.t1,
                    t2=idea.t2,
                    box_high=alert_dict['box_high'],
                    box_low=alert_dict['box_low'],
                    range_pct=alert_dict['range_pct'],
                    atr_ratio=alert_dict['atr_ratio'],
                    vol_ratio=alert_dict['vol_ratio'],
                    break_vol_mult=alert_dict['break_vol_mult'],
                    extension_pct=alert_dict['extension_pct'],
                    market_bias=alert_dict['market_bias'],
                    vwap_ok=alert_dict['vwap_ok'],
                    alert_text_short=texts['short'],
                    alert_text_medium=texts['medium'],
                    alert_text_deep=texts['deep_dive'],
                    telegram_status_code=status_code,
                    telegram_response=tg_resp,
                )
                session.add(alert_row)
                session.flush()

                for op in option_payloads:
                    oc = OptionCandidate(alert_id=alert_row.id, **op)
                    session.add(oc)

                alerts_triggered.append({"symbol": symbol, "direction": idea.direction, "confidence": confidence})
            except Exception as exc:  # noqa: BLE001
                logger.exception(f"scan error for {symbol}: {exc}")
                errors += 1
                continue

        scan_run.finished_at = datetime.utcnow()
        scan_run.symbols_scanned = settings.universe_list()
        scan_run.errors_count = errors

    return {"alerts": alerts_triggered, "notes": scan_notes}


async def worker_loop() -> None:
    init_db()
    client = MassiveClient()
    while True:
        run_scan_once(client)
        await asyncio.sleep(settings.SCAN_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(worker_loop())

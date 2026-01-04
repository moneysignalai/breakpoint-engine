from __future__ import annotations

import asyncio
import platform
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Dict, List

from loguru import logger

from src.config import get_settings
from src.models.alert import Alert
from src.models.option_candidate import OptionCandidate
from src.models.scan_run import ScanRun
from src.services import alerts as alert_service
from src.services.db import session_scope, init_db
from src.services.market_time import in_allowed_window
from src.services.massive_client import MassiveClient, MassiveNotFoundError
from src.strategies.flagship import FlagshipStrategy
from src.strategies.option_optimizer import OptionOptimizer, OptionPick
from src.utils import configure_logging

configure_logging("worker")
settings = get_settings()
logger.info(
    "worker boot",
    settings=settings.non_secret_dict(),
    python_version=platform.python_version(),
)


def run_scan_once(client: MassiveClient | None = None) -> Dict[str, Any]:
    client = client or MassiveClient()
    strategy = FlagshipStrategy()
    optimizer = OptionOptimizer()

    started_at = datetime.utcnow()
    scan_notes = []
    alerts_triggered: List[Dict[str, Any]] = []
    universe = settings.universe_list()
    universe_count = len(universe)
    scanned_count = 0
    triggered_count = 0
    error_count = 0
    bars_404_count = 0
    scan_reason: str = "ok"
    start = time.monotonic()
    tz = ZoneInfo(settings.TIMEZONE)
    now = datetime.now(tz)

    def get_window_label() -> str:
        current_time = now.time()
        rth_start = current_time.replace(hour=9, minute=30, second=0, microsecond=0)
        rth_end = current_time.replace(hour=16, minute=0, second=0, microsecond=0)
        if rth_start <= current_time <= rth_end:
            return "RTH"
        if current_time < rth_start:
            return "PM"
        return "AH"

    window_label = get_window_label()

    logger.info(f"scan start | universe_count={universe_count} window={window_label}")
    result: Dict[str, Any] = {"alerts": alerts_triggered, "notes": scan_notes}

    def reason_from_exception(exc: Exception) -> str:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        if isinstance(exc, MassiveNotFoundError):
            return "404"
        if status_code is not None:
            return str(status_code)
        return exc.__class__.__name__

    def log_scan_end() -> None:
        duration_ms = int((time.monotonic() - start) * 1000)
        effective_reason = scan_reason
        if scanned_count == 0 and error_count > 0 and scan_reason == "ok":
            effective_reason = "api_error"

        if triggered_count == 0:
            logger.info(
                f"scan result | no alerts | scanned={scanned_count} reason={effective_reason}"
            )

        scan_end_message = (
            f"scan end | duration_ms={duration_ms} scanned={scanned_count} "
            f"triggered={triggered_count} errors={error_count} reason={effective_reason}"
        )

        if universe_count > 0 and scanned_count == 0:
            logger.warning(
                f"scan anomaly | universe_count={universe_count} scanned=0 reason={effective_reason}"
            )

        logger.info(scan_end_message)

    try:
        with session_scope() as session:
            scan_run = ScanRun(started_at=started_at, finished_at=None, universe=settings.UNIVERSE, symbols_scanned=[])
            session.add(scan_run)
            session.flush()

            allowed_window = in_allowed_window(now)
            if not allowed_window:
                scan_run.finished_at = datetime.utcnow()
                scan_run.notes = "Outside allowed window"
                result = {"alerts": [], "notes": "Outside allowed window"}
                if settings.SCAN_OUTSIDE_WINDOW:
                    scan_reason = "forced_outside_window"
                else:
                    scan_reason = "outside_window"
                    return result

            market_symbol = "QQQ"
            market_bars: List[Dict[str, Any]] = []
            try:
                market_bars_start = time.perf_counter()
                market_bars = client.get_bars(
                    market_symbol, timeframe="5m", limit=settings.BOX_BARS * 3
                )
                logger.info(
                    "market bars fetched",
                    symbol=market_symbol,
                    duration_ms=int((time.perf_counter() - market_bars_start) * 1000),
                    bars=len(market_bars),
                )
            except Exception as exc:  # noqa: BLE001
                error_count += 1
                scan_reason = "api_error"
                scan_run.finished_at = datetime.utcnow()
                scan_run.notes = "Market bars fetch failed"
                logger.warning(
                    "scan symbol error",
                    symbol=market_symbol,
                    stage="bars",
                    reason=reason_from_exception(exc),
                )
                if isinstance(exc, MassiveNotFoundError):
                    bars_404_count += 1
                logger.exception("market bars fetch failed", symbol=market_symbol)
                return result

            for symbol in universe:
                scanned_count += 1
                symbol_error_recorded = False

                def record_symbol_error(stage: str, exc: Exception) -> None:
                    nonlocal symbol_error_recorded, bars_404_count, error_count
                    if not symbol_error_recorded:
                        error_count += 1
                        symbol_error_recorded = True
                    reason = reason_from_exception(exc)
                    logger.warning(
                        "scan symbol error",
                        symbol=symbol,
                        stage=stage,
                        reason=reason,
                    )
                    logger.debug(
                        "scan symbol error detail",
                        symbol=symbol,
                        stage=stage,
                        error=str(exc),
                    )
                    if isinstance(exc, MassiveNotFoundError) and stage == "bars":
                        bars_404_count += 1

                try:
                    bars_start = time.perf_counter()
                    try:
                        bars = client.get_bars(
                            symbol, timeframe="5m", limit=settings.BOX_BARS * 3
                        )
                    except Exception as exc:  # noqa: BLE001
                        record_symbol_error("bars", exc)
                        continue
                    logger.info(
                        "bars fetched",
                        symbol=symbol,
                        duration_ms=int((time.perf_counter() - bars_start) * 1000),
                        bars=len(bars),
                    )

                    daily_start = time.perf_counter()
                    try:
                        daily = client.get_daily_snapshot(symbol)
                    except Exception as exc:  # noqa: BLE001
                        record_symbol_error("daily", exc)
                        continue
                    logger.debug(
                        "daily snapshot fetched",
                        symbol=symbol,
                        duration_ms=int((time.perf_counter() - daily_start) * 1000),
                    )

                    idea = strategy.evaluate(symbol, bars, daily, market_bars)
                    if not idea:
                        logger.info("strategy skipped", symbol=symbol)
                        continue

                    logger.info(
                        "strategy passed",
                        symbol=symbol,
                        direction=idea.direction,
                        confidence=idea.confidence,
                    )

                    expirations_start = time.perf_counter()
                    try:
                        expirations = client.get_option_expirations(symbol)
                    except Exception as exc:  # noqa: BLE001
                        record_symbol_error("options_expirations", exc)
                        continue
                    logger.info(
                        "expirations fetched",
                        symbol=symbol,
                        duration_ms=int((time.perf_counter() - expirations_start) * 1000),
                        expirations=len(expirations),
                    )
                    iv_pct = daily.get("iv_percentile") if isinstance(daily, dict) else None

                    def load_chain(exp: str):
                        chain_start = time.perf_counter()
                        try:
                            chain = client.get_option_chain(symbol, exp)
                        except Exception as exc:  # noqa: BLE001
                            record_symbol_error("options_chain", exc)
                            raise
                        logger.debug(
                            "option chain fetched",
                            symbol=symbol,
                            expiration=exp,
                            duration_ms=int((time.perf_counter() - chain_start) * 1000),
                            contracts=len(chain),
                        )
                        return chain

                    try:
                        bars_ts = (
                            bars[-1]["ts"]
                            if isinstance(bars[-1]["ts"], datetime)
                            else datetime.fromisoformat(bars[-1]["ts"])
                        )
                        opt_result = optimizer.run(
                            symbol,
                            idea.direction,
                            idea.expected_window,
                            bars_ts,
                            expirations,
                            load_chain,
                            iv_percentile=iv_pct,
                        )
                    except Exception as exc:  # noqa: BLE001
                        record_symbol_error("optimizer", exc)
                        continue

                    confidence = idea.confidence
                    option_picks: List[OptionPick] = []
                    if opt_result.stock_only:
                        confidence = max(0.0, confidence - 1.0)
                        idea.debug["debug_reasons"].append(
                            opt_result.reason or "stock-only"
                        )
                    else:
                        option_picks = opt_result.candidates

                    logger.info(
                        "optimizer result",
                        symbol=symbol,
                        stock_only=opt_result.stock_only,
                        candidate_count=len(option_picks),
                    )

                    if confidence < settings.MIN_CONFIDENCE_TO_ALERT:
                        logger.info(
                            "alert threshold not met",
                            symbol=symbol,
                            confidence=confidence,
                            min_confidence=settings.MIN_CONFIDENCE_TO_ALERT,
                        )
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
                        "box_high": idea.debug["box_high"],
                        "box_low": idea.debug["box_low"],
                        "range_pct": idea.debug["range_pct"],
                        "atr_ratio": idea.debug["atr_ratio"],
                        "vol_ratio": idea.debug["vol_ratio"],
                        "break_vol_mult": idea.debug["break_vol_mult"],
                        "extension_pct": idea.debug["extension_pct"],
                        "market_bias": idea.debug.get("market_bias"),
                        "vwap_ok": idea.debug["vwap_ok"],
                    }
                    option_payloads = []
                    if option_picks:
                        for pick in option_picks:
                            option_payloads.append(
                                {
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
                                }
                            )

                    texts = alert_service.build_alert_texts(
                        alert_dict, option_payloads if option_payloads else None
                    )
                    try:
                        status_code, tg_resp = alert_service.send_telegram_message(
                            texts["short"]
                        )
                    except Exception as exc:  # noqa: BLE001
                        record_symbol_error("alert_send", exc)
                        logger.info(
                            f"alert send result | symbol={symbol} channel=telegram result=failed status_code=None reason={str(exc)}"
                        )
                        continue
                    sent_success = status_code == 200
                    if status_code is None:
                        reason = tg_resp or "no-status"
                    elif status_code != 200:
                        reason = f"status_code={status_code}"
                    else:
                        reason = "ok"
                    if not sent_success:
                        record_symbol_error("alert_send", RuntimeError(reason))
                    logger.info(
                        f"alert send result | symbol={symbol} channel=telegram result={'sent' if sent_success else 'failed'} status_code={status_code} reason={reason}"
                    )
                    logger.debug("telegram response", symbol=symbol, response=tg_resp)

                    alert_row = Alert(
                        symbol=symbol,
                        direction=idea.direction,
                        confidence=confidence,
                        expected_window=idea.expected_window,
                        entry=idea.entry,
                        stop=idea.stop,
                        t1=idea.t1,
                        t2=idea.t2,
                        box_high=alert_dict["box_high"],
                        box_low=alert_dict["box_low"],
                        range_pct=alert_dict["range_pct"],
                        atr_ratio=alert_dict["atr_ratio"],
                        vol_ratio=alert_dict["vol_ratio"],
                        break_vol_mult=alert_dict["break_vol_mult"],
                        extension_pct=alert_dict["extension_pct"],
                        market_bias=alert_dict["market_bias"],
                        vwap_ok=alert_dict["vwap_ok"],
                        alert_text_short=texts["short"],
                        alert_text_medium=texts["medium"],
                        alert_text_deep=texts["deep_dive"],
                        telegram_status_code=status_code,
                        telegram_response=tg_resp,
                    )
                    session.add(alert_row)
                    session.flush()
                    logger.info("alert persisted", symbol=symbol, alert_id=alert_row.id)

                    for op in option_payloads:
                        oc = OptionCandidate(alert_id=alert_row.id, **op)
                        session.add(oc)

                    alerts_triggered.append(
                        {"symbol": symbol, "direction": idea.direction, "confidence": confidence}
                    )
                    if sent_success:
                        triggered_count += 1
                except Exception as exc:  # noqa: BLE001
                    if not symbol_error_recorded:
                        record_symbol_error("unexpected", exc)
                    logger.exception("scan error for symbol", symbol=symbol, error=str(exc))
                    continue
            if bars_404_count > 1:
                logger.warning(
                    "Massive bars endpoint returned 404 (check MASSIVE_BARS_PATH_TEMPLATE)"
                )

            scan_run.finished_at = datetime.utcnow()
            scan_run.symbols_scanned = universe
            scan_run.errors_count = error_count

        result = {"alerts": alerts_triggered, "notes": scan_notes}
    except Exception as exc:  # noqa: BLE001
        scan_reason = "api_error"
        logger.exception("scan failed", error=str(exc))
        result = {"alerts": alerts_triggered, "notes": scan_notes}
    finally:
        log_scan_end()

    return result


async def worker_loop() -> None:
    init_db()
    client = MassiveClient()
    while True:
        try:
            run_scan_once(client)
        except Exception as exc:  # noqa: BLE001
            logger.exception("worker loop error", error=str(exc))
        await asyncio.sleep(settings.SCAN_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(worker_loop())

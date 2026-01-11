from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import List
from zoneinfo import ZoneInfo

from loguru import logger

from src.config import get_settings
from src.utils.math import mid_price

settings = get_settings()


@dataclass
class OptionContract:
    contract_symbol: str
    expiry: str
    strike: float
    call_put: str
    bid: float
    ask: float
    volume: int
    oi: int
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    iv: float | None = None
    iv_percentile: float | None = None

    @property
    def mid(self) -> float:
        return mid_price(self.bid, self.ask)

    @property
    def spread_pct(self) -> float:
        mid = self.mid or 0.01
        return (self.ask - self.bid) / max(mid, 0.01)


@dataclass
class OptionPick:
    tier: str
    contract: OptionContract
    rationale: str
    exit_plan: str


@dataclass
class OptionResult:
    stock_only: bool
    reason: str | None
    candidates: List[OptionPick]


class OptionOptimizer:
    def __init__(self, tz: str | None = None):
        self.tz = ZoneInfo(tz or settings.TIMEZONE)

    def select_expirations(self, expirations: List[str], trigger_time: datetime, expected_window: str) -> List[str]:
        filtered = []
        for exp in expirations:
            try:
                exp_dt = datetime.fromisoformat(exp)
            except Exception:
                continue
            dte = (exp_dt.date() - trigger_time.date()).days
            if trigger_time.time() < time(14, 0):
                if 3 <= dte <= 7:
                    filtered.append(exp)
            else:
                if 1 <= dte <= 3:
                    filtered.append(exp)
            if expected_window == "1_3_days" and 3 <= dte <= 10 and exp not in filtered:
                filtered.append(exp)
        return filtered or expirations[:3]

    def filter_contract(self, contract: OptionContract) -> bool:
        lenient_mode = bool(getattr(settings, "DEBUG_LENIENT_MODE", False))
        min_volume = settings.MIN_OPT_VOLUME * (0.5 if lenient_mode else 1.0)
        min_oi = settings.MIN_OPT_OI * (0.5 if lenient_mode else 1.0)
        min_mid = settings.MIN_OPT_MID * (0.5 if lenient_mode else 1.0)
        spread_max = settings.SPREAD_PCT_MAX * (1.4 if lenient_mode else 1.0)

        if contract.bid <= 0 or contract.ask <= 0:
            return False
        if contract.spread_pct > spread_max:
            return False
        if contract.volume < min_volume and contract.oi < min_oi:
            return False
        if contract.mid < min_mid:
            return False
        return True

    def pick_by_delta(self, contracts: List[OptionContract], target_low: float, target_high: float) -> OptionContract | None:
        best = None
        best_score = -1.0
        target_mid = (target_low + target_high) / 2
        for c in contracts:
            if c.delta is None:
                continue
            if not (target_low <= abs(c.delta) <= target_high):
                continue
            score = 1 - abs(abs(c.delta) - target_mid)
            score += max(0, 1 - c.spread_pct)
            score += (c.volume + c.oi) / 1000.0
            if c.gamma:
                score += c.gamma
            if score > best_score:
                best = c
                best_score = score
        return best

    def fallback_by_moneyness(self, contracts: List[OptionContract], target: str) -> OptionContract | None:
        if not contracts:
            return None
        sorted_contracts = sorted(contracts, key=lambda c: abs(c.strike))
        return sorted_contracts[0]

    def build_candidates(self, contracts: List[OptionContract]) -> List[OptionContract]:
        contracts = [c for c in contracts if self.filter_contract(c)]
        return contracts

    def run(self, symbol: str, direction: str, expected_window: str, trigger_time: datetime, expirations: List[str], chain_loader, iv_percentile: float | None = None) -> OptionResult:
        trigger_time = trigger_time.astimezone(self.tz)
        if iv_percentile is not None and iv_percentile > settings.IV_PCTL_MAX_FOR_ANY:
            return OptionResult(stock_only=True, reason="IV too high; skipping options", candidates=[])

        preferred_exps = self.select_expirations(expirations, trigger_time, expected_window)
        all_candidates: List[OptionContract] = []
        for exp in preferred_exps:
            chain_data = chain_loader(exp)
            for c in chain_data:
                if direction == 'LONG' and c.get('type', c.get('call_put', 'C')).upper().startswith('P'):
                    continue
                if direction == 'SHORT' and c.get('type', c.get('call_put', 'C')).upper().startswith('C'):
                    continue
                contract = OptionContract(
                    contract_symbol=c.get('symbol') or c.get('contract_symbol') or '',
                    expiry=exp,
                    strike=float(c['strike']),
                    call_put='CALL' if (c.get('type') or c.get('call_put', 'C')).upper().startswith('C') else 'PUT',
                    bid=float(c['bid']),
                    ask=float(c['ask']),
                    volume=int(c.get('volume') or 0),
                    oi=int(c.get('oi') or c.get('open_interest') or 0),
                    delta=c.get('delta'),
                    gamma=c.get('gamma'),
                    theta=c.get('theta'),
                    iv=c.get('iv'),
                    iv_percentile=c.get('iv_percentile'),
                )
                all_candidates.append(contract)

        filtered = self.build_candidates(all_candidates)
        logger.debug(
            "option optimizer filter summary",
            symbol=symbol,
            total_contracts=len(all_candidates),
            filtered_contracts=len(filtered),
            lenient_mode=bool(getattr(settings, "DEBUG_LENIENT_MODE", False)),
        )
        if not filtered:
            return OptionResult(stock_only=True, reason="No liquid contracts", candidates=[])

        tiers = {
            'Conservative': (0.50, 0.65),
            'Standard': (0.35, 0.50),
            'Aggressive': (0.25, 0.35),
        }
        picks: List[OptionPick] = []

        disabled_aggressive = iv_percentile is not None and iv_percentile > settings.IV_PCTL_MAX_FOR_AGG

        for tier, band in tiers.items():
            if tier == 'Aggressive' and disabled_aggressive:
                continue
            contract = self.pick_by_delta(filtered, band[0], band[1])
            if not contract:
                contract = self.fallback_by_moneyness(filtered, tier)
            if contract:
                rationale = f"Delta in {band[0]:.2f}-{band[1]:.2f}, spread {contract.spread_pct*100:.1f}%"
                picks.append(OptionPick(tier=tier, contract=contract, rationale=rationale, exit_plan="Take 40-60% at T1, runner to T2"))

        if disabled_aggressive:
            while len(picks) < 3:
                picks.append(picks[-1])
        if len(picks) == 0:
            return OptionResult(stock_only=True, reason="No suitable contracts", candidates=[])
        while len(picks) < 3:
            picks.append(picks[-1])

        return OptionResult(stock_only=False, reason=None, candidates=picks[:3])

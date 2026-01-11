from __future__ import annotations

from datetime import datetime, timedelta

from loguru import logger

from src.config import get_settings
from src.models.alert import Alert
from src.models.grade import Grade
from src.services.db import session_scope
from src.services.massive_client import MassiveClient
from src.strategies.flagship import Bar

settings = get_settings()


def compute_grade_for_alert(alert: Alert, client: MassiveClient) -> Grade:
    bars = client.get_bars(alert.symbol, timeframe="5m", limit=150)
    entry = alert.entry
    t1 = alert.t1
    t2 = alert.t2
    hit_t1 = False
    hit_t2 = False
    mfe = 0.0
    mae = 0.0
    time_to_t1 = None
    time_to_t2 = None

    for idx, bar in enumerate(bars):
        if isinstance(bar, Bar):
            high = bar.high
            low = bar.low
        else:
            high = bar.get('high')
            low = bar.get('low')
        if alert.direction == 'LONG':
            mfe = max(mfe, (high - entry) / entry)
            mae = min(mae, (low - entry) / entry)
            if not hit_t1 and high >= t1:
                hit_t1 = True
                time_to_t1 = idx * 5
            if not hit_t2 and high >= t2:
                hit_t2 = True
                time_to_t2 = idx * 5
        else:
            mfe = max(mfe, (entry - low) / entry)
            mae = min(mae, (entry - high) / entry)
            if not hit_t1 and low <= t1:
                hit_t1 = True
                time_to_t1 = idx * 5
            if not hit_t2 and low <= t2:
                hit_t2 = True
                time_to_t2 = idx * 5

    return Grade(
        alert_id=alert.id,
        hit_t1=hit_t1 if hit_t1 else False,
        hit_t2=hit_t2 if hit_t2 else False,
        mfe_stock_pct=mfe if mfe != 0 else None,
        mae_stock_pct=mae if mae != 0 else None,
        time_to_t1_min=time_to_t1,
        time_to_t2_min=time_to_t2,
    )


def grade_alerts(days: int = 3) -> None:
    client = MassiveClient()
    cutoff = datetime.utcnow() - timedelta(days=days)
    with session_scope() as session:
        alerts = session.query(Alert).filter(Alert.created_at >= cutoff).all()
        for alert in alerts:
            grade = compute_grade_for_alert(alert, client)
            session.add(grade)
            logger.info(f"Graded alert {alert.symbol} {alert.id}")


if __name__ == "__main__":
    grade_alerts()

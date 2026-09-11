"""Startup-owned adapters for fixed, non-refreshing research reads."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo


def stored_research_alerts(query_strict, ticker):
    rows = query_strict(
        "SELECT under, exp AS expiry, bias, conviction, asof_ts FROM flow_alerts_daily "
        "WHERE under = ? AND asof_date >= ? ORDER BY asof_ts DESC LIMIT 200",
        [ticker, (datetime.now(UTC) - timedelta(days=7)).date().isoformat()],
    )
    for row in rows:
        stamp = row.get("asof_ts")
        # Legacy TIMESTAMP stores the producer's exchange-local wall time:
        # flow_alerts.persist_alerts casts datetime.now(_ET).isoformat().
        if isinstance(stamp, datetime) and stamp.tzinfo is None:
            row["asof_ts"] = stamp.replace(tzinfo=ZoneInfo("America/New_York")).astimezone(UTC)
    return rows

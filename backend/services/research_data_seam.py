"""Startup-owned adapters for fixed, non-refreshing research reads."""

import json
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo


def stored_research_alerts(query_strict, ticker):
    rows = query_strict(
        "SELECT under, exp AS expiry, bias, conviction, asof_ts, context_json FROM flow_alerts_daily "
        "WHERE under = ? AND asof_date >= ? ORDER BY asof_ts DESC LIMIT 200",
        [ticker, (datetime.now(UTC) - timedelta(days=7)).date().isoformat()],
    )
    for row in rows:
        stamp = row.get("asof_ts")
        # Legacy TIMESTAMP stores the producer's exchange-local wall time:
        # flow_alerts.persist_alerts casts datetime.now(_ET).isoformat().
        if isinstance(stamp, datetime) and stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=ZoneInfo("America/New_York")).astimezone(UTC)
        row["computed_at"] = stamp
        # An alert's creation time cannot freshen its underlying market input.
        # Legacy rows lack verified producer time and remain unavailable to the
        # fresh-direction calculation until provenance is present.
        try:
            context = json.loads(row.pop("context_json") or "{}")
        except (ValueError, TypeError):
            context = {}
        from services.market_provenance import timestamp
        observed = timestamp(context.get("source_event_time")) if isinstance(context, dict) and context.get("source_quality") == "ok" else None
        row["asof_ts"] = observed
    return rows

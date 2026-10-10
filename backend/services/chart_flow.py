"""B20 flow buckets: call up/put down, hash equality, explicit unknowns."""
from __future__ import annotations

import hashlib
import json


def bucket_hash(bar_id, window, filters) -> str:
    """Equal filter/cursor hash for drilldown and totals."""
    raw = json.dumps({"bar": bar_id, "window": window, "filters": filters or {}}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def bucketize(trades: list[dict]):
    """Sum call premium above zero, put below; unknown classifications explicit."""
    call = sum(t.get("premium", 0) for t in (trades or []) if t.get("side") == "call")
    put = sum(t.get("premium", 0) for t in (trades or []) if t.get("side") == "put")
    unknown = [t for t in (trades or []) if t.get("side") not in ("call", "put")]
    return {"call_premium": call, "put_premium": -abs(put), "count": len(trades or []),
            "unknown": len(unknown), "top": sorted(trades or [], key=lambda t: t.get("premium", 0), reverse=True)[:3]}

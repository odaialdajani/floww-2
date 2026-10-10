"""G1 scope parity: explicit query_key selects scope X even with newer Y present.

Direct build_history characterization: the scope-selection contract the
PriceNodeHistory forcedScope prop relies on. Synthetic rows only.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from services.price_node_history import build_history, scope_id  # noqa: E402


def _row(sid, asof, qk, walls):
    import json
    return {"snapshot_id": sid, "ticker": "SPY", "query_key": qk,
            "expiries": ["2026-10-17"], "formula_version": "gex.v2",
            "exposure_basis": "gb", "asof_ts": asof, "received_at": asof,
            "walls_json": json.dumps(walls)}


def _bars():
    return [
        {"t": "2026-10-06T13:30:00+00:00", "o": 100.0, "h": 102.0, "l": 99.0, "c": 101.0},
        {"t": "2026-10-06T13:31:00+00:00", "o": 101.0, "h": 103.0, "l": 100.0, "c": 102.0},
    ]


def test_explicit_scope_x_wins_over_newer_y():
    x = _row("sx", "2026-10-06T13:29:00+00:00", "KX",
             [{"wall_id": "wx", "mid": 100.5}])
    y = _row("sy", "2026-10-06T13:30:30+00:00", "KY",
             [{"wall_id": "wy", "mid": 999.0}])
    xid = scope_id(x)
    out = build_history("SPY", _bars(), [x, y], query_key=xid)
    assert out["query_key"] == xid
    assert out["frames"][0]["snapshot_id"] == "sx"
    assert out["frames"][0]["nodes"][0]["id"] == "wx"
    assert all(f["snapshot_id"] == "sx" for f in out["frames"] if f["nodes"])


def test_default_latest_scope_unchanged():
    x = _row("sx", "2026-10-06T13:29:00+00:00", "KX",
             [{"wall_id": "wx", "mid": 100.5}])
    y = _row("sy", "2026-10-06T13:30:30+00:00", "KY",
             [{"wall_id": "wy", "mid": 999.0}])
    out = build_history("SPY", _bars(), [x, y])
    assert out["query_key"] == scope_id(y)
    # Y is not yet known at the first candle: no nodes (known-at discipline),
    # nodes appear once the snapshot is time-eligible.
    assert out["frames"][0]["snapshot_id"] is None
    assert out["frames"][1]["snapshot_id"] == "sy"

"""G5 exposure centre from RECORDED strikes (signed net gex, S2 dollars).

Centre = sum(strike*w)/sum(|w|); upper/lower split at centre. Empty,
zero-mass, unsigned-only, or non-finite rows yield None — never a carry.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from services.chart_exposure_centre import exposure_centre  # noqa: E402


def test_signed_weighted_centre():
    rows = [{"strike": 100.0, "gex": -100.0}, {"strike": 110.0, "gex": 50.0}]
    out = exposure_centre(rows)
    assert out["centre"] == (100.0 * -100.0 + 110.0 * 50.0) / 150.0
    assert out["upper"] == -30.0
    assert out["lower"] is None
    assert out["status"] == "recorded"


def test_empty_zero_unsigned_yield_none():
    assert exposure_centre([])["centre"] is None
    assert exposure_centre([{"strike": 100.0, "gex": 0.0}])["centre"] is None
    assert exposure_centre([{"strike": 100.0}])["centre"] is None
    assert exposure_centre([{"strike": -5.0, "gex": 10.0}])["centre"] is None
    assert exposure_centre([{"strike": "x", "gex": 10.0}])["centre"] is None


def test_call_put_fallback_when_no_net():
    rows = [{"strike": 100.0, "call_gex": 30.0, "put_gex": -10.0}]
    out = exposure_centre(rows)
    assert out["centre"] == 100.0


def test_build_history_emits_per_candle_exposure_line():
    import json

    from services.price_node_history import build_history
    strikes = json.dumps([{"strike": 100.0, "gex": -100.0},
                          {"strike": 110.0, "gex": 50.0}])
    rows = [{"snapshot_id": "s1", "ticker": "SPY", "query_key": "K",
             "expiries": ["2026-10-17"], "formula_version": "gex.v2",
             "exposure_basis": "gb", "asof_ts": "2026-10-06T13:29:00+00:00",
             "received_at": "2026-10-06T13:29:00+00:00",
             "walls_json": "[]", "strikes_json": strikes}]
    bars = [
        {"t": "2026-10-06T13:30:00+00:00", "o": 100.0, "h": 102.0,
         "l": 99.0, "c": 101.0},
        {"t": "2026-10-06T13:31:00+00:00", "o": 101.0, "h": 103.0,
         "l": 100.0, "c": 102.0},
    ]
    out = build_history("SPY", bars, rows)
    assert len(out["exposure_line"]) == 2
    assert out["exposure_line"][0] == {"time": out["frames"][0]["time"],
                                       "centre": -30.0, "upper": -30.0,
                                       "lower": None}
    assert out["frames"][1]["exposure_centre"] == -30.0
    assert out["frames"][1]["exposure_upper"] == -30.0


def test_no_usable_snapshot_yields_null_centres():
    from services.price_node_history import build_history
    bars = [{"t": "2026-10-06T13:30:00+00:00", "o": 100.0, "h": 102.0,
             "l": 99.0, "c": 101.0}]
    out = build_history("SPY", bars, [])
    assert out["exposure_line"] == [{"time": out["frames"][0]["time"],
                                     "centre": None, "upper": None,
                                     "lower": None}]

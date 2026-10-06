"""S2 governed window-activity surface (Spark).

The window metric Σ c·u·|δ|·ΔV is only defined between comparable
observations. These pin the comparability gate (ticker/provider/scope/
formula/session/ordering) and the refusal to emit a number — in any form —
when the window is not a window (R10-07 class defect: SPY→QQQ produced 150).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.solstice_window import (  # noqa: E402
    check_window_comparability,
    window_activity_surface,
)

META_PREV = {
    "ticker": "SPY", "data_source": "public_api", "scope_key": "SPY:day:0:60",
    "formula_version": "gex.v2", "session_date": "2030-01-02",
    "asof": "2030-01-02T14:00:00+00:00",
}
META_CUR = {
    **META_PREV, "asof": "2030-01-02T14:01:00+00:00",
}


def _c(volume, **kw):
    base = {
        "osi": "SPY300101C00299000", "strike": 300, "expiry": "2030-01-05",
        "type": "call", "gamma": 0.01, "delta": 0.5, "multiplier": 100.0,
        "volume": volume, "oi": 100, "greeks_source": "vendor",
    }
    base.update(kw)
    return base


def test_comparability_rejects_each_identity_mismatch():
    assert check_window_comparability(META_PREV, META_CUR) == (None, None)
    for field, code in (
        ("ticker", "TICKER_MISMATCH"),
        ("data_source", "PROVIDER_MISMATCH"),
        ("scope_key", "SCOPE_MISMATCH"),
        ("formula_version", "FORMULA_MISMATCH"),
        ("session_date", "SESSION_ROLL"),
    ):
        reason, _ = check_window_comparability(META_PREV, {**META_CUR, field: "OTHER"})
        assert reason == code, field
    out_of_order = {**META_CUR, "asof": META_PREV["asof"]}
    assert check_window_comparability(META_PREV, out_of_order)[0] == "SOURCE_OUT_OF_ORDER"


def test_cross_ticker_window_yields_no_number():
    out = window_activity_surface(META_PREV, {**META_CUR, "ticker": "QQQ"},
                                  [_c(100)], [_c(200)], 300.0)
    assert out["status"] == "unavailable"
    assert out["reason"] == "TICKER_MISMATCH"
    assert out["window_net"] is None and out["window_gross_like"] is None
    assert out["contracts"] == []


def test_missing_baseline_and_spot_are_unavailable():
    out = window_activity_surface(META_PREV, META_CUR, [], [_c(200)], 300.0)
    assert out["reason"] == "NO_BASELINE"
    assert out["window_net"] is None
    spotless = window_activity_surface(META_PREV, META_CUR, [_c(100)], [_c(200)], None)
    assert spotless["reason"] == "SPOT_UNKNOWN"
    assert spotless["window_net"] is None


def test_volume_retraction_never_produces_negative_or_zero_flow():
    out = window_activity_surface(META_PREV, META_CUR, [_c(200)], [_c(100)], 300.0)
    assert out["status"] == "unavailable"
    assert out["reason"] == "VOLUME_REBASE"
    assert out["window_net"] is None


def test_valid_window_reports_surface_coverage_and_convention():
    out = window_activity_surface(META_PREV, META_CUR, [_c(100)], [_c(200)], 300.0)
    assert out["status"] == "ok"
    assert out["greek_convention"].startswith("frozen-open")
    assert "not buyer-minus-seller flow" in out["provenance_note"]
    assert out["interval"] == {"start": META_PREV["asof"], "end": META_CUR["asof"]}
    assert out["coverage"]["n_comparable_contracts"] == 1
    # u = 0.01*100*300^2*0.01 = 900; |d|=.5; dV=100 -> 45,000 call
    assert out["window_net"] == 45_000.0
    assert out["window_gross_like"] == 45_000.0
    assert out["surface"]["strikes"][0]["window_net"] == 45_000.0
    assert out["surface"]["cells"] == [
        {"expiry": "2030-01-05", "strike": "300.0", "window_dadgex": 45_000.0}
    ]


def test_missing_delta_is_excluded_and_counted_not_zeroed():
    prev = [_c(100), _c(100, osi="SPY300101P00299000", type="put", delta=None)]
    cur = [_c(200), _c(200, osi="SPY300101P00299000", type="put", delta=None)]
    out = window_activity_surface(META_PREV, META_CUR, prev, cur, 300.0)
    assert out["status"] == "ok"
    assert out["coverage"]["n_missing_delta"] == 1
    assert out["coverage"]["n_comparable_contracts"] == 1
    assert out["window_net"] == 45_000.0  # the unknown-delta leg contributes nothing

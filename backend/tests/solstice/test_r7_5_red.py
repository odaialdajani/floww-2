"""R7-05 red tests: review workflow inputs (shortlist rows)."""

import sys

sys.path.insert(0, "backend")

import pytest


def _contract(**kw):
    c = {"osi": "OC1", "expiry": "2030-01-15", "strike": 500, "type": "call",
         "multiplier": 100.0, "bid": 1.0, "ask": 1.2, "mid": 1.1, "last": 1.1,
         "bid_size": 10, "ask_size": 10, "volume": 500, "open_interest": 1000,
         "iv": 0.2, "delta": 0.45, "gamma": 0.05, "T": 30 / 365,
         "bid_timestamp": "2030-01-02T14:00:00+00:00",
         "ask_timestamp": "2030-01-02T14:00:00+00:00"}
    c.update(kw)
    return c


def test_shortlist_rows_bounded_and_typed():
    from services.contract_scout import scout_candidates, scout_shortlist_rows
    cons = [_contract(osi=f"C{i}", delta=0.40 + i * 0.02) for i in range(5)]
    res = scout_candidates(cons, "CALLS", 500.0)
    assert res["n_eligible"] == 5
    rows = scout_shortlist_rows(res, "CALLS", n=3)
    assert len(rows) == 3
    r = rows[0]
    # Ranked closest to |delta| 0.5 first: C4 (0.48), not input order.
    assert r["osi"] == "C4" and r["expiry"] == "2030-01-15" and r["strike"] == 500
    assert r["side"] == "CALLS" and r["delta"] == pytest.approx(0.48)
    assert r["bid"] == 1.0 and r["ask"] == 1.2
    assert abs(r["spread_pct"] - (0.2 / 1.1 * 100)) < 1e-9
    assert r["tick_size"] is None and r["tick_unknown"] is True
    assert r["bid_ts"] == "2030-01-02T14:00:00+00:00"
    # No-candidate stays a valid empty list, never an exception.
    empty = scout_candidates([], "PUTS", 500.0)
    assert scout_shortlist_rows(empty, "PUTS") == []
    assert empty["no_candidate_is_valid"] is True

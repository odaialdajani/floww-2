"""R5-D red tests: strict 0DTE production context (G5/R11-R13)."""

import sys

sys.path.insert(0, "backend")


def _c(**kw):
    base = {"osi": "X", "type": "call", "strike": 500, "bid": 1.0, "ask": 1.2,
            "bid_timestamp": "2030-01-02T14:00:00+00:00",
            "ask_timestamp": "2030-01-02T14:00:00+00:00",
            "delta": 0.5, "gamma": 0.05, "volume": 500, "T": 0.5 / 365,
            "expiry": "2030-01-02"}
    base.update(kw)
    return base


def _now(s):
    from datetime import UTC, datetime
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt.timestamp() if dt.tzinfo else dt.replace(tzinfo=UTC).timestamp()


def test_r11_strict_context_rejects_missing_timestamps():
    from services.contract_scout import scout_candidates
    now = _now("2030-01-02T14:00:10+00:00")
    c = _c(bid_timestamp=None, ask_timestamp=None)
    r = scout_candidates([c], "CALLS", 500.0, now_s=now, session_date="2030-01-02")
    assert r["n_eligible"] == 0, r
    assert r["rejected"].get("STALE_BID") == 1 or r["rejected"].get("STALE_ASK") == 1


def test_r11_production_callers_pass_session_context():
    import inspect

    import routes.solstice as rs
    import server
    assert "session_date" in inspect.getsource(rs.scout)
    src = inspect.getsource(server._build_heatmap_impl)
    assert src.count("session_date") >= 2


def test_r13_preopen_and_ineligible_quality_block_entry():
    from datetime import UTC, datetime

    from services.solstice_session import session_state
    pre = datetime(2030, 1, 2, 12, 0, tzinfo=UTC)  # 07:00 ET pre-open
    s = session_state(now=pre, quality={"state": "usable", "reasonCodes": [],
                                        "setupEligible": True})
    assert s["entry_allowed"] is False
    assert s["management_allowed"] is True
    mid = datetime(2030, 1, 2, 15, 0, tzinfo=UTC)  # 10:00 ET open
    s2 = session_state(now=mid, quality={"state": "usable", "reasonCodes": [],
                                         "setupEligible": False})
    assert s2["entry_allowed"] is False
    s3 = session_state(now=mid, quality={"state": "usable", "reasonCodes": [],
                                         "setupEligible": True})
    assert s3["entry_allowed"] is True

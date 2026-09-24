"""P06 red-first tests (R4-08/09). Each fails on baseline behavior."""

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
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.timestamp()


def test_r4_08_stale_quotes_rejected_despite_valid_numbers():
    from services.contract_scout import scout_candidates
    now = _now("2030-01-02T14:01:00+00:00")
    c = _c(bid_timestamp="2030-01-02T13:00:00+00:00",
           ask_timestamp="2030-01-02T13:00:00+00:00")
    r = scout_candidates([c], "CALLS", 500.0, max_stale_s=30.0, now_s=now)
    assert r["n_eligible"] == 0, r
    assert r["rejected"].get("STALE_BID") or r["rejected"].get("STALE_ASK")


def test_r4_08_nan_quotes_rejected():
    from services.contract_scout import scout_candidates
    now = _now("2030-01-02T14:00:10+00:00")
    r = scout_candidates([_c(bid=float("nan"))], "CALLS", 500.0, now_s=now)
    assert r["n_eligible"] == 0
    r2 = scout_candidates([_c(ask=float("nan"))], "CALLS", 500.0, now_s=now)
    assert r2["n_eligible"] == 0


def test_r4_08_later_expiry_excluded():
    from services.contract_scout import scout_candidates
    now = _now("2030-01-02T14:00:10+00:00")
    c = _c(expiry="2030-01-03")  # not same-day
    r = scout_candidates([c], "CALLS", 500.0, now_s=now,
                         session_date="2030-01-02")
    assert r["n_eligible"] == 0
    assert r["rejected"].get("NO_0DTE_LISTING") == 1


def test_r4_09_saturday_blocks_entry():
    from datetime import UTC, datetime

    from services.solstice_session import session_state
    sat = datetime(2030, 1, 5, 15, 0, tzinfo=UTC)  # Saturday
    s = session_state(now=sat, quality={"state": "usable", "reasonCodes": []})
    assert s["entry_allowed"] is False
    assert s["management_allowed"] is True  # block never abandons positions


def test_r4_09_unknown_quality_fails_closed():
    from datetime import UTC, datetime

    from services.solstice_session import session_state
    wed = datetime(2030, 1, 2, 15, 0, tzinfo=UTC)  # Wednesday, mid-session
    s = session_state(now=wed, quality={"state": "unknown", "reasonCodes": []})
    assert s["entry_allowed"] is False

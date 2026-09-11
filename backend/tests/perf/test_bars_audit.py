"""
D-audit of B1 market_bars vs CONTRACTS C13 (Agent D). B-owned module,
read-only: C13 shape, budget exercised on miss, stale-serve, ADV honesty,
cross-agreement with D3 validators. Characterization pins (green on
existing behavior); divergences filed in LEDGER, not pinned.
"""
from __future__ import annotations

import asyncio
import sys
from unittest.mock import patch


def _ensure_imports():
    if "services.market_bars" not in sys.modules:
        sys.path.insert(0, "/Users/nav/Documents/GitHub/floww/backend")


_ensure_imports()

TICKER = "ZZB1"  # never a real universe ticker


def _bar(t, o=100.0, h=101.0, lo=99.0, c=100.5, v=1000):
    return {"t": t, "o": o, "h": h, "l": lo, "c": c, "v": v}


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class _Budget:
    def __init__(self):
        self.acquires = 0

    async def acquire(self, host="public"):
        self.acquires += 1

    def release(self):
        pass


def _setup(monkey_rows, budget=None):
    from services import market_bars as mb

    mb._reset_state()

    async def upstream(ticker, period, aggregation, sessions="regular"):
        return [dict(r) if isinstance(r, dict) else r for r in monkey_rows]

    p1 = patch.object(mb, "_upstream", upstream)
    p2 = patch.object(mb, "_budget", budget or _Budget())
    p1.start()
    p2.start()
    return mb, (p1, p2)


def _teardown(handles):
    for p in handles:
        p.stop()


def test_c13_shape_and_d3_cross_agreement():
    from services.contract_validators import validate_bar

    rows = [_bar("2026-09-04T10:00:00-04:00"),
            _bar("2026-09-04T10:01:00-04:00", h=50.0),  # high<low-ish violation
            "junk",
            _bar("2026-09-04T10:02:00-04:00", v=-3)]  # negative volume
    mb, h = _setup(rows)
    try:
        got = _run(mb.get_1min_bars(TICKER, days=1))
        assert got is not None and len(got) == 1
        assert set(got[0]) == {"t", "o", "h", "l", "c", "v"}
        assert validate_bar(got[0])[0] is True  # D3 agrees: survivors are clean
        assert mb.quarantine_counts().get("total", 0) >= 3
    finally:
        _teardown(h)


def test_budget_exercised_on_miss_not_on_hit():
    b = _Budget()
    mb, h = _setup([_bar("2026-09-04T10:00:00-04:00")], budget=b)
    try:
        assert _run(mb.get_1min_bars(TICKER, days=1)) is not None
        assert b.acquires == 1
        assert _run(mb.get_1min_bars(TICKER, days=1)) is not None
        assert b.acquires == 1, "cache hit must not re-acquire"
    finally:
        _teardown(h)


def test_all_bad_cold_returns_none_with_reason_never_raises():
    mb, h = _setup(["junk", {"o": 1}])
    try:
        got = _run(mb.get_1min_bars(TICKER, days=1))
        assert got is None
        assert mb.last_error().get("reason") == "all-quarantined"
    finally:
        _teardown(h)


def test_adv_honest_thresholds():
    mb, h = _setup([_bar(f"2026-08-{d:02d}T10:00:00-04:00", v=1000 * d) for d in range(1, 22)])
    try:
        adv = _run(mb.get_adv_21d(TICKER))
        assert adv is not None and abs(adv - 11000.0) < 1e-6
    finally:
        _teardown(h)
    mb2, h2 = _setup([_bar(f"2026-09-{d:02d}T10:00:00-04:00", v=500) for d in range(1, 6)])
    try:
        assert _run(mb2.get_adv_21d(TICKER)) is None  # <10 sessions: unknown
    finally:
        _teardown(h2)

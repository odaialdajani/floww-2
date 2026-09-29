"""Resweep: the defects this second adversarial pass actually found.

Each test here fails on the pre-fix code and binds to a specific defect,
not to a helper calling itself:

H1  the window comparability gate was FAIL-OPEN: an identity field absent
    on either side skipped its check, so an undeclared window produced a
    number (500.0 for a window with no declared ticker on the current side).
H2  the keyed cache was UNBOUNDED: 500 distinct scopes left 500 entries and
    500 per-key locks, and expired entries were never reclaimed.
H3  a cache hit reported WHEN IT WAS CACHED nowhere, so a consumer could
    read a fresh timestamp off a stale payload.
H4  a cache hit returned the cursor captured when those rows were computed
    and presented it as the live rotation checkpoint.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import solstice_scan as scan  # noqa: E402
from services.solstice_rank import KeyedScanCache  # noqa: E402
from services.solstice_window import (  # noqa: E402
    IDENTITY_FIELDS,
    check_window_comparability,
    window_activity_surface,
)

META_PREV = {
    "ticker": "SPY", "data_source": "public_api", "scope_key": "SPY:day:0:60",
    "formula_version": "gex.v2", "session_date": "2030-01-02",
    "asof": "2030-01-02T14:00:00+00:00",
}
META_CUR = {**META_PREV, "asof": "2030-01-02T14:01:00+00:00"}


def _c(volume):
    return [{"osi": "SPY3000102C00300000", "strike": 300, "expiry": "2030-01-05",
             "type": "call", "gamma": 0.01, "delta": 0.5, "volume": volume,
             "oi": 100, "multiplier": 100}]


# ---- H1: fail-closed comparability ----

def test_undeclared_identity_is_not_a_match():
    for field, _reason in IDENTITY_FIELDS:
        for drop in ("prev", "cur"):
            prev = {k: v for k, v in META_PREV.items() if not (drop == "prev" and k == field)}
            cur = {k: v for k, v in META_CUR.items() if not (drop == "cur" and k == field)}
            reason, detail = check_window_comparability(prev, cur)
            assert reason == "IDENTITY_UNDECLARED", (field, drop, reason)
            assert field in detail


def test_empty_string_identity_is_also_undeclared():
    assert check_window_comparability({**META_PREV, "ticker": "  "}, META_CUR)[0] == "IDENTITY_UNDECLARED"
    assert check_window_comparability(META_PREV, {**META_CUR, "data_source": ""})[0] == "IDENTITY_UNDECLARED"


def test_undeclared_window_produces_no_number():
    out = window_activity_surface({"ticker": "SPY"}, {}, _c(10), _c(20), 100.0)
    assert out["status"] == "unavailable"
    assert out["reason"] == "IDENTITY_UNDECLARED"
    assert out["window_net"] is None and out["window_gross_like"] is None
    assert out["contracts"] == []


def test_unparseable_asof_is_undeclared_not_silently_accepted():
    bad = {**META_CUR, "asof": "not-a-timestamp"}
    assert check_window_comparability(META_PREV, bad)[0] == "IDENTITY_UNDECLARED"
    assert check_window_comparability({**META_PREV, "asof": None}, META_CUR)[0] == "IDENTITY_UNDECLARED"


def test_declared_and_equal_still_passes():
    assert check_window_comparability(META_PREV, META_CUR) == (None, None)
    # ticker comparison is case-insensitive, everything else is exact
    assert check_window_comparability({**META_PREV, "ticker": "spy"},
                                      {**META_CUR, "ticker": "SPY"}) == (None, None)


# ---- H2/H3: bounded cache, honest cache metadata ----

def test_cache_is_bounded_and_reclaims_expired_entries():
    cache = KeyedScanCache(ttl_s=300.0, max_entries=64)

    async def comp():
        return {"v": 1}

    async def main():
        for i in range(500):
            await cache.get_or_compute_async(f"k{i}", comp)
        return len(cache._entries), len(cache._async_locks), cache.evictions

    entries, locks, evictions = asyncio.run(main())
    assert entries <= 64, f"cache grew to {entries} entries; it must be bounded"
    assert locks <= 64, f"{locks} per-key locks retained; they must be reclaimed"
    assert evictions > 0, "eviction must be reported, not silent"


def test_evicting_an_expired_entry_only_forces_recompute():
    cache = KeyedScanCache(ttl_s=0.0, max_entries=4)

    async def comp():
        return {"v": 1}

    async def main():
        for i in range(10):
            await cache.get_or_compute_async(f"k{i}", comp)
        return await cache.get_or_compute_async("k0", comp)

    out = asyncio.run(main())
    assert out["cache"] == "miss", "an expired entry must be recomputed, not served"
    assert out["v"] == 1


def test_a_hit_reports_when_it_was_cached_not_now():
    cache = KeyedScanCache(ttl_s=300.0)
    first = cache.get_or_compute("k", lambda: {"source_asof": "t0"})
    hit = cache.get_or_compute("k", lambda: {"source_asof": "t1"})
    assert hit["cache"] == "hit"
    assert hit["source_asof"] == "t0"
    assert hit["cached_at"] == first["cached_at"]
    assert hit["cached_at"] <= first["cached_at"] + 0.001


# ---- H4: a cache hit must not report a stale cursor as the live one ----

def test_cache_hit_reports_the_live_cursor_and_labels_the_stale_one():
    scan._CURSOR.clear()
    scan._CACHE._entries.clear()
    scan._CACHE._async_locks.clear()

    async def fake_batch(tickers, **kw):
        return {"rows": [{"ticker": t, "flow": {"conviction": 50}} for t in tickers],
                "coverage": {}, "skipped": []}

    import services.universe_scan as us

    original = us.scan_batch
    us.scan_batch = fake_batch
    try:
        first = asyncio.run(scan.run_scan(universe="popular", limit=2, opportunity_fn=None))
        assert first["cache"] == "miss"
        assert first["cursor"]["cursor_stale"] is False
        payload_position = first["cursor"]["payload_position"]

        # Move the live cursor on (as a resumed sweep would), then hit the cache.
        asyncio.run(scan._advance_cursor("popular:None:2", payload_position + 4))
        second = asyncio.run(scan.run_scan(universe="popular", limit=2, opportunity_fn=None))
        assert second["cache"] == "hit"
        assert second["cursor"]["position"] == payload_position + 4, (
            "a hit must report the LIVE checkpoint, not the one captured with the payload"
        )
        assert second["cursor"]["payload_position"] == payload_position
        assert second["cursor"]["cursor_stale"] is True
    finally:
        us.scan_batch = original
        scan._CURSOR.clear()
        scan._CACHE._entries.clear()

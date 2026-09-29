"""The scanner's rotating cursor must actually rotate (U1).

`prefilter_universe` truncates its ranked list to `limit`, and
`routes.flowseeker.universe_scan` then walks that already-truncated list with
a module-level cursor. Because the list length equals `limit`, the cursor's
`(start + take) % n` wraps straight back to zero: every call rescans the same
top-ranked batch and the rest of the universe is never reached.

Reproduction of the audited counterexample: universe of five, limit two,
three calls -> AAA/BBB every time, 2/5 coverage.

The test drives the real `prefilter_universe` and the real route arithmetic.
Prioritization and full-universe rotation are separate concerns: the prefilter
should return a stable ordering of everything eligible, and the route should
take a window from it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.universe_scan import prefilter_universe  # noqa: E402


def _route_batches(universe, limit, calls):
    """The route's own cursor arithmetic, driven by the real prefilter."""
    pre = prefilter_universe(list(universe), movers={}, prior={},
                             flow_alert_tickers=set(), limit=limit)
    ordered = [r["ticker"] for r in pre["ordered"]]
    n = len(ordered)
    cursor = 0
    batches = []
    for _ in range(calls):
        start = cursor % n
        take = min(len(ordered), max(1, limit))
        batches.append([ordered[(start + k) % n] for k in range(take)])
        cursor = (start + take) % n
    return pre, batches


def test_prefilter_returns_the_whole_eligible_universe_not_just_limit():
    """A universe larger than `limit` must not be silently truncated here.

    If the prefilter keeps only `limit`, no cursor can ever reach the rest.
    """
    universe = ["AAA", "BBB", "CCC", "DDD", "EEE"]
    pre = prefilter_universe(list(universe), movers={}, prior={},
                             flow_alert_tickers=set(), limit=2)
    kept = [r["ticker"] for r in pre["ordered"]]
    assert len(kept) == len(universe), (
        f"prefilter kept {len(kept)} of {len(universe)} eligible names "
        f"({kept}); batch size must not decide universe coverage"
    )
    assert pre["coverage"]["kept"] == len(universe)


def test_cursor_rotates_through_the_whole_universe():
    """Five names, limit two, three calls must not rescan one batch."""
    universe = ["AAA", "BBB", "CCC", "DDD", "EEE"]
    _pre, batches = _route_batches(universe, limit=2, calls=3)
    assert not all(b == batches[0] for b in batches), (
        f"every call returned {batches[0]}; the cursor never advanced"
    )


def test_three_batches_cover_five_of_five_names():
    """The audited counterexample, as a regression guard."""
    universe = ["AAA", "BBB", "CCC", "DDD", "EEE"]
    _pre, batches = _route_batches(universe, limit=2, calls=3)
    scanned = {t for b in batches for t in b}
    assert scanned == set(universe), (
        f"three batches of 2 covered {sorted(scanned)} of {universe}"
    )


def test_priority_ordering_is_still_deterministic_and_ranked():
    """Rotation must not destroy prioritization: order stays score-desc."""
    out = prefilter_universe(
        ["SPY", "QQQ", "IWM"],
        movers={"SPY": 5.0, "QQQ": 0.1, "IWM": 9.9},
        prior={}, flow_alert_tickers=set(), limit=3,
    )
    order = [r["ticker"] for r in out["ordered"]]
    assert order == ["IWM", "SPY", "QQQ"], f"ranking changed: {order}"


def test_excluded_names_stay_excluded_from_rotation():
    """Exclusions must not re-enter through a wider kept list."""
    out = prefilter_universe(
        ["SPY", "BTC", "QQQ"],
        movers={}, prior={}, flow_alert_tickers=set(), limit=3,
    )
    kept = {r["ticker"] for r in out["ordered"]}
    excluded = {r["ticker"] for r in out["excluded"]}
    assert not (kept & excluded), f"a name is both kept and excluded: {kept & excluded}"

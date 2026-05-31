"""
backend/tests/services/test_gex_history.py

Unit tests for the GEX history backfill pipeline:
  - ``services.gex_history.compute_gex_total_for_chain``
  - ``services.gex_history.build_gex_history``
  - ``services.ml.features.fetch_gex_history_from_mongo``

All Mongo interactions use ``unittest.mock.MagicMock`` so the test suite does
NOT depend on a live Atlas connection. No synthetic market data is invented —
the fixtures construct minimal-but-realistic ``databento_eod_chains`` /
``underlying_bars`` documents whose only purpose is to exercise the math and
the chain/bar-intersection logic.
"""

from __future__ import annotations

import math
import sys
from datetime import date

# Make ``services`` and ``services.ml`` importable when pytest is launched
# from anywhere in the repo. We need ``backend/`` on sys.path so that
# ``services.gex_history`` resolves; from this file that is parent.parent.parent
# (services -> tests -> backend).
from pathlib import Path  # noqa: E402
from typing import Any, Dict, Iterable, List

import pandas as pd
import pytest
from scipy.stats import norm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from services.gex_history import (  # noqa: E402
    _IV_FALLBACK,
    _MIN_T_YEARS,
    _OPTION_MULTIPLIER,
    _PCT_MOVE,
    _RISK_FREE,
    build_gex_history,
    compute_gex_total_for_chain,
)
from services.ml.features import (  # noqa: E402
    add_gex_features,
    fetch_gex_history_from_mongo,
)

# ────────────────────────────────────────────────────────────────────────────
# Helpers — fake Mongo + math reference


def _bs_gamma(spot: float, strike: float, T: float, iv: float = _IV_FALLBACK,
              r: float = _RISK_FREE) -> float:
    """Reference Black-Scholes gamma (q=0). Kept independent of the module
    under test so the hand-computed expected value below is genuinely an
    independent check, not a tautology."""
    d1 = (math.log(spot / strike) + (r + 0.5 * iv * iv) * T) / (iv * math.sqrt(T))
    return float(norm.pdf(d1) / (spot * iv * math.sqrt(T)))


def _expected_gex(spot: float, contracts: List[Dict[str, Any]],
                  day_iso: str) -> float:
    """Reference per-day gex_total mirroring the module's math, computed via
    a different control path (Python list + math, not numpy vectors)."""
    today = date.fromisoformat(day_iso)
    total = 0.0
    for c in contracts:
        k = float(c["strike"])
        oi = float(c["oi"])
        if k <= 0 or oi <= 0:
            continue
        try:
            T = max(
                (date.fromisoformat(c["expiry"]) - today).days / 365.0,
                _MIN_T_YEARS,
            )
        except (KeyError, ValueError):
            T = 0.25
        sign = 1.0 if str(c.get("type", "")).lower() in ("call", "c") else -1.0
        g = _bs_gamma(spot, k, T)
        total += sign * g * oi * _OPTION_MULTIPLIER * spot * _PCT_MOVE
    return total


class _FakeCursor:
    """Iterable that supports the ``find(...)`` shape used in the codebase
    (returns documents; projections are ignored — we just yield what we have).
    Supports both sync and async iteration for Motor cursor compatibility."""

    def __init__(self, docs: Iterable[Dict[str, Any]]):
        self._docs = list(docs)

    def __iter__(self):
        return iter(self._docs)

    def __aiter__(self):
        self._aiter_idx = 0
        return self

    async def __anext__(self):
        if self._aiter_idx >= len(self._docs):
            raise StopAsyncIteration
        doc = self._docs[self._aiter_idx]
        self._aiter_idx += 1
        return doc


class _FakeCollection:
    def __init__(self, docs: List[Dict[str, Any]]):
        self.docs = docs

    def find(self, query: Dict[str, Any] = None, projection=None):
        # Tiny filter engine — supports our two query shapes:
        #   {"ticker": "SPY", "date": {"$gte": s, "$lte": e}}
        #   {"ticker": "SPY", "ts":   {"$gte": s, "$lte": e}}
        if not query:
            return _FakeCursor(self.docs)
        out: List[Dict[str, Any]] = []
        for d in self.docs:
            ok = True
            for key, val in query.items():
                if isinstance(val, dict):
                    field_val = d.get(key)
                    if field_val is None:
                        ok = False
                        break
                    gte = val.get("$gte")
                    lte = val.get("$lte")
                    if gte is not None and field_val < gte:
                        ok = False
                        break
                    if lte is not None and field_val > lte:
                        ok = False
                        break
                else:
                    if d.get(key) != val:
                        ok = False
                        break
            if ok:
                out.append(d)
        return _FakeCursor(out)


class _FakeDB:
    """Dict-of-collections shim that satisfies ``db[name].find(...)``."""

    def __init__(self, collections: Dict[str, List[Dict[str, Any]]]):
        self._colls = {k: _FakeCollection(v) for k, v in collections.items()}

    def __getitem__(self, name: str) -> _FakeCollection:
        return self._colls.setdefault(name, _FakeCollection([]))


def _make_chain(day: str, contracts_list: List[Dict[str, Any]],
                ticker: str = "SPY") -> Dict[str, Any]:
    """Wrap a list of contracts into a databento_eod_chains-shaped doc."""
    contracts_dict = {
        f"sym_{i}": c for i, c in enumerate(contracts_list)
    }
    return {"ticker": ticker, "day": day, "contracts": contracts_dict}


def _make_bar(day: str, close: float, ticker: str = "SPY") -> Dict[str, Any]:
    return {"ticker": ticker, "date": day, "close": float(close)}


# ────────────────────────────────────────────────────────────────────────────
# Test 1 — hand-computed expected value


def test_compute_gex_total_two_calls_two_puts_matches_hand_math():
    """Synthetic chain (2 calls + 2 puts) → gex_total matches the
    independent Black-Scholes reference computed in `_expected_gex`."""
    spot = 500.0
    contracts = [
        {"strike": 495.0, "oi": 1000, "expiry": "2024-03-15", "type": "call"},
        {"strike": 505.0, "oi": 1500, "expiry": "2024-03-15", "type": "call"},
        {"strike": 495.0, "oi": 800,  "expiry": "2024-03-15", "type": "put"},
        {"strike": 505.0, "oi": 1200, "expiry": "2024-03-15", "type": "put"},
    ]
    chain = _make_chain("2024-02-01", contracts)
    expected = _expected_gex(spot, contracts, "2024-02-01")
    got = compute_gex_total_for_chain(chain, spot)
    assert math.isclose(got, expected, rel_tol=1e-9, abs_tol=1e-9), (
        f"got {got} expected {expected}"
    )
    # Sanity: with equal-ish call/put OI bracketing spot, the signed sum
    # should be non-zero (calls outweigh puts here).
    assert got != 0.0


# ────────────────────────────────────────────────────────────────────────────
# Test 2 — zero contracts


def test_compute_gex_total_zero_contracts_returns_zero():
    chain = _make_chain("2024-02-01", [])
    assert compute_gex_total_for_chain(chain, 500.0) == 0.0
    # And the same when `contracts` is missing entirely.
    chain_missing = {"ticker": "SPY", "day": "2024-02-01"}
    assert compute_gex_total_for_chain(chain_missing, 500.0) == 0.0


# ────────────────────────────────────────────────────────────────────────────
# Test 3 — missing gamma/open_interest do not crash


def test_compute_gex_total_missing_fields_no_crash(caplog):
    """Contracts with missing or zero OI / strike are silently skipped —
    the function must not raise, and the result equals the sum over the
    remaining well-formed contracts."""
    spot = 500.0
    contracts = [
        # Well-formed — should contribute.
        {"strike": 500.0, "oi": 1000, "expiry": "2024-03-15", "type": "call"},
        # Missing oi.
        {"strike": 510.0, "expiry": "2024-03-15", "type": "call"},
        # Zero strike.
        {"strike": 0,    "oi": 1000, "expiry": "2024-03-15", "type": "put"},
        # Non-dict contract value — must be ignored without crashing.
        # (We can't easily set this through _make_chain — patch directly.)
    ]
    chain = _make_chain("2024-02-01", contracts)
    chain["contracts"]["bogus"] = "not-a-dict"
    chain["contracts"]["empty_oi"] = {"strike": 520.0, "oi": 0,
                                       "expiry": "2024-03-15", "type": "call"}
    # None for oi.
    chain["contracts"]["null_oi"] = {"strike": 530.0, "oi": None,
                                      "expiry": "2024-03-15", "type": "put"}

    got = compute_gex_total_for_chain(chain, spot)
    # Only the first contract is valid → result equals its single-strike gex.
    expected = _expected_gex(spot, [contracts[0]], "2024-02-01")
    assert math.isclose(got, expected, rel_tol=1e-9, abs_tol=1e-9)


# ────────────────────────────────────────────────────────────────────────────
# Test 4 — 5 chains + 5 matching bars → 5 rows


@pytest.mark.asyncio
async def test_build_gex_history_five_aligned_days():
    days = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"]
    chains = [
        _make_chain(d, [
            {"strike": 470.0, "oi": 1000, "expiry": "2024-03-15", "type": "call"},
            {"strike": 470.0, "oi": 800,  "expiry": "2024-03-15", "type": "put"},
        ])
        for d in days
    ]
    bars = [_make_bar(d, 470.0 + i) for i, d in enumerate(days)]
    db = _FakeDB({"databento_eod_chains": chains, "underlying_bars": bars})

    rows = await build_gex_history(
        "SPY", start_date=date(2024, 1, 1), end_date=date(2024, 1, 31),
        mongo_db=db,
    )
    assert len(rows) == 5
    # Each row has the contract shape advertised in the module docstring.
    for r in rows:
        assert set(r.keys()) >= {"ts", "gex_total", "spot"}
        assert isinstance(r["ts"], str) and r["ts"].endswith("+00:00")
        assert isinstance(r["gex_total"], float)
        assert r["spot"] > 0


# ────────────────────────────────────────────────────────────────────────────
# Test 5 — mismatched dates (intersection only)


@pytest.mark.asyncio
async def test_build_gex_history_intersection_only():
    """3 chains, 2 bars; the 2 days that overlap must be the ONLY rows. The
    third chain day has no bar → must be dropped (no synthesis)."""
    chain_days = ["2024-01-02", "2024-01-03", "2024-01-04"]
    bar_days = ["2024-01-02", "2024-01-03"]  # missing 01-04
    chains = [
        _make_chain(d, [
            {"strike": 470.0, "oi": 500, "expiry": "2024-03-15", "type": "call"},
        ])
        for d in chain_days
    ]
    bars = [_make_bar(d, 470.0) for d in bar_days]
    db = _FakeDB({"databento_eod_chains": chains, "underlying_bars": bars})

    rows = await build_gex_history(
        "SPY", start_date=date(2024, 1, 1), end_date=date(2024, 1, 31),
        mongo_db=db,
    )
    assert len(rows) == 2
    got_days = [r["ts"][:10] for r in rows]
    assert got_days == ["2024-01-02", "2024-01-03"]


# ────────────────────────────────────────────────────────────────────────────
# Test 6 — empty Mongo


@pytest.mark.asyncio
async def test_build_gex_history_empty_mongo():
    db = _FakeDB({"databento_eod_chains": [], "underlying_bars": []})
    rows = await build_gex_history(
        "SPY", start_date=date(2024, 1, 1), end_date=date(2024, 1, 31),
        mongo_db=db,
    )
    assert rows == []


# ────────────────────────────────────────────────────────────────────────────
# Test 7 — chronological order independent of Mongo iteration order


@pytest.mark.asyncio
async def test_build_gex_history_sorted_regardless_of_mongo_order():
    days = ["2024-01-04", "2024-01-02", "2024-01-08", "2024-01-03"]  # scrambled
    chains = [
        _make_chain(d, [
            {"strike": 470.0, "oi": 500, "expiry": "2024-03-15", "type": "call"},
        ])
        for d in days
    ]
    bars = [_make_bar(d, 470.0) for d in days]  # scrambled too
    db = _FakeDB({"databento_eod_chains": chains, "underlying_bars": bars})

    rows = await build_gex_history(
        "SPY", start_date=date(2024, 1, 1), end_date=date(2024, 1, 31),
        mongo_db=db,
    )
    ts_list = [r["ts"] for r in rows]
    assert ts_list == sorted(ts_list), (
        f"build_gex_history must emit rows in chronological order, got {ts_list}"
    )


# ────────────────────────────────────────────────────────────────────────────
# Test 8 — fetch_gex_history_from_mongo applies the `ts <= as_of` filter


def test_fetch_gex_history_no_future_leakage():
    """The query must include ``ts <= as_of`` so a row dated AFTER as_of
    cannot appear in the result. We assert this by populating the fake DB
    with a future row and verifying it is excluded."""
    rows = [
        {"ticker": "SPY", "ts": "2024-01-02T00:00:00+00:00", "gex_total": 1.0},
        {"ticker": "SPY", "ts": "2024-01-03T00:00:00+00:00", "gex_total": 2.0},
        {"ticker": "SPY", "ts": "2024-01-04T00:00:00+00:00", "gex_total": 3.0},  # future
    ]
    db = _FakeDB({"gex_history": rows})
    as_of = pd.Timestamp("2024-01-03T00:00:00+00:00")
    got = fetch_gex_history_from_mongo(
        "SPY", as_of=as_of, lookback_days=60, mongo_db=db,
    )
    ts_list = [r["ts"] for r in got]
    assert all(t <= as_of.isoformat() for t in ts_list), (
        f"fetch returned future rows: {ts_list}"
    )
    assert "2024-01-04T00:00:00+00:00" not in ts_list


# ────────────────────────────────────────────────────────────────────────────
# Test 9 — lookback_days window is respected


def test_fetch_gex_history_lookback_window():
    """A lookback of 5 days at as_of=2024-01-10 must exclude 2024-01-01
    (9 days back) and include 2024-01-08 (2 days back)."""
    rows = [
        {"ticker": "SPY", "ts": "2024-01-01T00:00:00+00:00", "gex_total": 1.0},
        {"ticker": "SPY", "ts": "2024-01-08T00:00:00+00:00", "gex_total": 2.0},
        {"ticker": "SPY", "ts": "2024-01-09T00:00:00+00:00", "gex_total": 3.0},
        {"ticker": "SPY", "ts": "2024-01-10T00:00:00+00:00", "gex_total": 4.0},
    ]
    db = _FakeDB({"gex_history": rows})
    as_of = pd.Timestamp("2024-01-10T00:00:00+00:00")
    got = fetch_gex_history_from_mongo(
        "SPY", as_of=as_of, lookback_days=5, mongo_db=db,
    )
    got_ts = [r["ts"] for r in got]
    assert "2024-01-01T00:00:00+00:00" not in got_ts  # outside window
    assert "2024-01-08T00:00:00+00:00" in got_ts
    assert "2024-01-10T00:00:00+00:00" in got_ts


# ────────────────────────────────────────────────────────────────────────────
# Test 10 — round-trip: write via build_gex_history → fetch via mongo → feed
# to add_gex_features. Confirms the shape contract end-to-end.


@pytest.mark.asyncio
async def test_round_trip_build_fetch_add_gex_features():
    days = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"]
    chains = [
        _make_chain(d, [
            {"strike": 470.0, "oi": 1000, "expiry": "2024-03-15", "type": "call"},
            {"strike": 470.0, "oi": 1000, "expiry": "2024-03-15", "type": "put"},
        ])
        for d in days
    ]
    bars = [_make_bar(d, 470.0 + i * 0.5) for i, d in enumerate(days)]
    write_db = _FakeDB({"databento_eod_chains": chains, "underlying_bars": bars})

    rows = await build_gex_history(
        "SPY", start_date=date(2024, 1, 1), end_date=date(2024, 1, 31),
        mongo_db=write_db,
    )
    assert len(rows) == 5

    # Stage the build_gex_history output into a `gex_history` fake collection
    # exactly the way the backfill script would (add ticker field).
    staged = [{"ticker": "SPY", **r} for r in rows]
    read_db = _FakeDB({"gex_history": staged})

    as_of = pd.Timestamp("2024-01-08T00:00:00+00:00")
    history = fetch_gex_history_from_mongo(
        "SPY", as_of=as_of, lookback_days=30, mongo_db=read_db,
    )
    # Shape contract: every entry is a dict with `ts` and `gex_total`.
    assert all(isinstance(h, dict) for h in history)
    assert all({"ts", "gex_total"} <= set(h.keys()) for h in history)
    assert len(history) == 5

    # Plug into add_gex_features: one current row + a gex_history column. The
    # function must accept the shape and emit the documented columns.
    df = pd.DataFrame([{
        "ticker": "SPY",
        "ts": as_of.isoformat(),
        "spot": 470.0,
        "gex_total": rows[-1]["gex_total"],
        # Pre-filter to ts <= row.ts (leakage contract; here all rows qualify).
        "gex_history": history,
    }])
    out = add_gex_features(df)
    # Documented output columns must all be present.
    for col in (
        "gex_zscore_60d",
        "gex_roc_5d",
        "gex_regime_pos",
        "gex_distance_to_flip_norm",
        "gex_wall_density_pct",
        "gex_herfindahl",
    ):
        assert col in out.columns, f"add_gex_features missed {col}"


# ────────────────────────────────────────────────────────────────────────────
# Test 11 — bonus: spot <= 0 short-circuits to 0.0 (defensive)


def test_compute_gex_total_zero_spot_returns_zero():
    chain = _make_chain("2024-02-01", [
        {"strike": 500.0, "oi": 1000, "expiry": "2024-03-15", "type": "call"},
    ])
    assert compute_gex_total_for_chain(chain, 0.0) == 0.0
    assert compute_gex_total_for_chain(chain, -1.0) == 0.0
    assert compute_gex_total_for_chain(chain, None) == 0.0


# ────────────────────────────────────────────────────────────────────────────
# Test 12 — bonus: end_date < start_date returns []


@pytest.mark.asyncio
async def test_build_gex_history_inverted_range_empty():
    db = _FakeDB({"databento_eod_chains": [], "underlying_bars": []})
    rows = await build_gex_history(
        "SPY", start_date=date(2024, 6, 1), end_date=date(2024, 1, 1),
        mongo_db=db,
    )
    assert rows == []

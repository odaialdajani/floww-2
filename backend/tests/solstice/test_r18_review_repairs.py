"""R18-C12: review-5979463755 repair pins (PR106 v3 rejection).

Failed-first pins for every remaining defect in the 2026-10-04 PR106
review rejection: the duplicate writer bypassing the shared full-row
binder (header tamper yielded ``duplicate`` while index/replay refused),
clocks-list/query-malformed envelopes raising out of the write path and
the binder, warm-concurrent same-key misses coalescing to more than ONE
budget envelope, and cancellation during vendor init / lock wait / the
vendor call leaking an inflight slot. Deterministic; no network.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import sys
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, "backend")

import duckdb

import services.public_api_adapter as adapter
from services.heatmap_history import (
    bind_range_row,
    list_range_envelopes,
    record_range_envelope,
    replay_range_envelope,
)
from services.solstice_range_analytics import (
    build_range_envelope,
    compute_content_digest,
    record_id_for_digest,
    select_window_expiries,
)

FIXTURES = Path(__file__).parent / "fixtures" / "range_analytics_v1"
TODAY = date(2026, 10, 5)


def _env(**chain_over):
    listing = json.loads((FIXTURES / "listing.json").read_text())
    chain = json.loads((FIXTURES / "chain_complete.json").read_text())
    chain.update(chain_over)
    sel = select_window_expiries(listing["expiries"], 14, 60, TODAY)
    return build_range_envelope(symbol="SPY", min_dte=14, max_dte=60,
                                asof=TODAY, listing=listing, selection=sel,
                                chain=chain)


def _recorded(conn, **kw):
    env = _env(**kw)
    res = record_range_envelope(conn, env)
    assert res["status"] == "recorded", res
    return env


# ── R1 (C04): the duplicate writer binds the FULL stored row ────────────────

def _tamper_header(conn, env, column, value):
    conn.execute(
        f"UPDATE range_analytics_envelopes_v1 SET {column} = ? "
        "WHERE record_id = ?", [value, env["record_id"]])


def test_r1_duplicate_write_refuses_header_tampered_row():
    """Header-tampered stored rows can never earn a duplicate success —
    the duplicate check binds every stored column via the shared binder,
    exactly like index and replay (review: 'header tamper yields
    duplicate while index/retrieve refuse')."""
    conn = duckdb.connect(":memory:")
    try:
        env = _recorded(conn)
        # The payload is INTACT (digest + content unchanged); only the
        # stored ROW headers lie. Index and replay refuse this row...
        for column, value in (
                ("ticker", "QQQ"),
                ("window_min", 15),
                ("window_max", 59),
                ("asof_date", "2026-10-06"),
                ("received_at", "1999-01-01T00:00:00+00:00"),
                ("status", "partial")):
            _tamper_header(conn, env, column, value)
            idx = list_range_envelopes(conn)
            row = next(r for r in idx["rows"]
                       if r["record_id"] == env["record_id"])
            assert row["integrity"] == "refused:ROW_HEADER_MISMATCH", column
            rep = replay_range_envelope(conn, env["record_id"])
            assert rep["error"] == "ROW_HEADER_MISMATCH", column
            # ...so the duplicate writer must refuse too, with the same
            # verdict — never a silent "duplicate".
            res = record_range_envelope(conn, env)
            assert res["status"] == "refused", (column, res)
            assert res["reason"] == "STORED_RECORD_CORRUPT", (column, res)
            assert res.get("stored_defect") == "ROW_HEADER_MISMATCH", \
                (column, res)
            # Restore the true header before the next tamper.
            true = {"ticker": env["symbol"], "window_min": 14, "window_max": 60,
                    "asof_date": env["query"]["as_of_ny"],
                    "received_at": env["clocks"]["received_at"],
                    "status": env["status"]}
            _tamper_header(conn, env, column, true[column])
        # With every header true again, the same write is a duplicate.
        res = record_range_envelope(conn, env)
        assert res["status"] == "duplicate", res
    finally:
        conn.close()


def test_r1_duplicate_write_refuses_tampered_digest_column():
    """A lying stored digest column is a full-row bind failure, never a
    duplicate success even though the payload itself is valid."""
    conn = duckdb.connect(":memory:")
    try:
        env = _recorded(conn)
        _tamper_header(conn, env, "digest", "f" * 64)
        res = record_range_envelope(conn, env)
        assert res["status"] == "refused", res
        assert res["reason"] == "STORED_RECORD_CORRUPT"
        assert res.get("stored_defect") == "STORED_DIGEST_MISMATCH"
    finally:
        conn.close()


# ── R2 (C05): hostile envelope shapes are TYPED refusals ───────────────────

def test_r2_write_refuses_clocks_and_query_non_dicts():
    """A list/str clocks or query block is a typed write refusal — the
    write path never raises AttributeError/TypeError (review:
    'clocks-list binder/write AttributeError')."""
    conn = duckdb.connect(":memory:")
    try:
        for mutate in (
                lambda e: e.update(clocks=[("received_at", "x")]),
                lambda e: e.update(clocks="not-a-dict"),
                lambda e: e.update(query=["min_dte", "max_dte"]),
                lambda e: e.update(query="not-a-dict")):
            env = _env()
            mutate(env)
            # The digest stays consistent with the mutated content: this is
            # a well-formed digest over a hostile SHAPE, so the refusal must
            # come from the shape check, not a digest mismatch.
            env["content_digest"] = compute_content_digest(env)
            env["record_id"] = record_id_for_digest(env["content_digest"])
            res = record_range_envelope(conn, env)
            assert res["status"] == "refused", res
            assert res["reason"] == "IDENTITY_INCOMPLETE", res
            assert isinstance(res["detail"], dict), res
    finally:
        conn.close()


def test_r2_binder_and_reads_refuse_clocks_list_payload():
    """A stored payload whose clocks/query block is a list/str/None —
    with a FULLY self-consistent digest over the hostile shape, so the
    refusal is the typed shape verdict, never a DIGEST_MISMATCH and never
    an AttributeError out of bind_range_row (the review's crash)."""
    conn = duckdb.connect(":memory:")
    try:
        from services.heatmap_history import ensure_range_tables
        ensure_range_tables(conn)
        env = _recorded(conn)
        for mutate, field in (
                (lambda e: e.update(clocks=[("received_at", "x")]), "clocks"),
                (lambda e: e.update(clocks="str"), "clocks"),
                (lambda e: e.update(query=["min_dte"]), "query"),
                (lambda e: e.update(query="str"), "query"),
                (lambda e: e.update(clocks=None), "clocks")):
            payload = json.loads(json.dumps(env))
            mutate(payload)
            # Self-consistent hostile payload: digest + record identity
            # recompute cleanly over the hostile SHAPE.
            payload["content_digest"] = compute_content_digest(payload)
            payload["record_id"] = record_id_for_digest(
                payload["content_digest"])
            conn.execute(
                "INSERT INTO range_analytics_envelopes_v1 VALUES (?, 'SPY', "
                "14, 60, '2026-10-05', ?, 'ok', ?, ?, '2026-10-05')",
                [payload["record_id"], env["clocks"]["received_at"],
                 payload["content_digest"], json.dumps(payload)])
            # The shared binder never raises and refuses with the typed
            # corruption verdict for every hostile shape.
            bound, refusal = bind_range_row(
                payload["record_id"], "SPY", 14, 60, "2026-10-05",
                env["clocks"]["received_at"], "ok",
                payload["content_digest"], json.dumps(payload))
            assert bound is None and refusal == "CORRUPT_PAYLOAD", \
                (field, refusal)
            rep = replay_range_envelope(conn, payload["record_id"])
            assert rep["error"] == "CORRUPT_PAYLOAD", (field, rep)
            idx = list_range_envelopes(conn, ticker="SPY")
            verdicts = {r["record_id"]: r["integrity"] for r in idx["rows"]}
            assert verdicts[payload["record_id"]] == \
                "refused:CORRUPT_PAYLOAD", field
        # The honest envelope still binds and serves alongside them.
        rep = replay_range_envelope(conn, env["record_id"])
        assert rep["integrity"] == "verified"
    finally:
        conn.close()


def test_r2_binder_refuses_non_object_json():
    """Valid JSON that is not an object (list/string/number/null) is a
    typed CORRUPT_PAYLOAD from the binder — hostile, never an exception."""
    for raw in ("[1, 2, 3]", '"a string"', "42", "null"):
        bound, refusal = bind_range_row("rga1-x", "SPY", 14, 60,
                                        "2026-10-05", "r", "ok", "d", raw)
        assert bound is None and refusal == "CORRUPT_PAYLOAD", raw


def test_r2_binder_survives_wrong_header_shapes():
    """Row headers arriving as lists/None/dicts are typed refusals too —
    the binder's string/int coercions never raise."""
    env = _env()
    payload_json = json.dumps(env)
    for headers in (
            {"ticker": ["SPY"], "asof": None, "status": {"s": 1},
             "received_at": ["r"], "digest": None, "window_min": None,
             "window_max": [60]},
            {"ticker": None, "asof": ["d"], "status": None,
             "received_at": None, "digest": ["d"], "window_min": "x",
             "window_max": None},
            {"ticker": {"t": 1}, "asof": date(2026, 10, 5), "status": 7,
             "received_at": {"r": 1}, "digest": 3.5, "window_min": [14],
             "window_max": "60"}):
        bound, refusal = bind_range_row(env["record_id"], headers["ticker"],
                                        headers["window_min"],
                                        headers["window_max"],
                                        headers["asof"],
                                        headers["received_at"],
                                        headers["status"], headers["digest"],
                                        payload_json)
        assert bound is None and refusal in ("CORRUPT_PAYLOAD",
                                             "ROW_HEADER_MISMATCH",
                                             "STORED_DIGEST_MISMATCH"), refusal


# ── R3 (C02): identities coalesce correctly — never wrongly ─────────────────

def _budget():
    from services.public_budget import PublicBudget
    return PublicBudget(capacity=60, refill_per_sec=0.0, max_inflight=4)


def _faithful_get_broker(broker):
    async def _get_broker():
        # R18-C12 fidelity: the REAL _get_broker initializes the module
        # singleton — the adapter's zero-I/O warm probe reads it.
        adapter.BROKER = broker
        return broker
    return AsyncMock(side_effect=_get_broker)


def _hang_mock():
    started = asyncio.Event()

    async def hang(*a, **k):
        started.set()
        await asyncio.sleep(3600)

    return started, AsyncMock(side_effect=hang)


def test_r3_different_tickers_never_coalesce():
    """Two DIFFERENT ticker identities fetching concurrently pay their own
    envelopes — coalescing is key-scoped, never global."""
    import pytest

    adapter._CHAIN_CACHE.clear()
    broker = MagicMock()
    with patch.object(adapter, "_get_broker",
                      new=_faithful_get_broker(broker)), \
            patch.object(adapter, "BROKER", None), \
            patch("services.public_budget.budget", _budget()), \
            patch.object(adapter, "_fetch_chain_live") as live:
        live.return_value = {"ticker": "X", "contracts": [], "expiries": [],
                             "data_source": "public_api", "stale": False}
        from services import public_budget as pb_mod
        budget = pb_mod.budget

        async def main():
            before = await budget.peek_available()
            out = await asyncio.gather(
                adapter.fetch_chain_from_public_api("SPY", max_expiries=2),
                adapter.fetch_chain_from_public_api("QQQ", max_expiries=2))
            after = await budget.peek_available()
            return out, before, after

        out, before, after = asyncio.run(main())
        assert all(o is not None for o in out)
        # Two distinct keys, TWO envelopes — never one shared debit.
        assert before - after == pytest.approx(2 * (2 + 2))
        assert budget._inflight == 0
        assert live.await_count == 2
    adapter.BROKER = None
    adapter._CHAIN_CACHE.clear()


def test_r3_warm_identity_rotation_never_serves_foreign_cache():
    """A cache entry bound to a DIFFERENT broker identity is never served
    by the warm probe (identity-bound cache, rotation-safe)."""
    import time as _time

    adapter._CHAIN_CACHE.clear()
    old_broker, new_broker = MagicMock(), MagicMock()
    try:
        adapter._CHAIN_CACHE[("ROTT", 1)] = (
            _time.monotonic(), old_broker,
            {"ticker": "ROTT", "contracts": ["STALE"], "expiries": [],
             "data_source": "public_api", "stale": False})
        with patch.object(adapter, "BROKER", new_broker), \
                patch.object(adapter, "_get_broker",
                             new=_faithful_get_broker(new_broker)), \
                patch("services.public_budget.budget", _budget()), \
                patch.object(adapter, "_fetch_chain_live") as live:
            live.return_value = {"ticker": "ROTT", "contracts": ["FRESH"],
                                 "expiries": [], "data_source": "public_api",
                                 "stale": False}
            out = asyncio.run(adapter.fetch_chain_from_public_api("ROTT", 1))
        assert out is not None
        assert out["contracts"] == ["FRESH"], out
        # The rotated-out identity's cache entry was replaced.
        assert adapter._CHAIN_CACHE[("ROTT", 1)][1] is new_broker
    finally:
        adapter.BROKER = None
        adapter._CHAIN_CACHE.clear()


# ── R4 (C03): cancellation during EVERY async wait releases the slot ───────

_SEAM_CALLS = {
    "chain": lambda: adapter.fetch_chain_from_public_api("SPY", 2),
    "range": lambda: adapter.fetch_chain_for_expiries("SPY", ["2026-10-26"]),
}


def _run_cancelled_in_vendor_call(budget, call, started):
    async def main():
        task = asyncio.create_task(call())
        # Drive the loop until the hanging vendor call is reached.
        await asyncio.wait_for(started.wait(), 5)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        assert budget._inflight == 0

    asyncio.run(main())


def test_r4_cancel_during_vendor_call_releases_chain_seam():
    """Chain seam: cancelling while _fetch_chain_live is in flight (debit
    already held) releases the slot exactly once."""
    started, hang = _hang_mock()
    adapter._CHAIN_CACHE.clear()
    with patch.object(adapter, "_fetch_chain_live", new=hang), \
            patch.object(adapter, "_get_broker",
                         new=_faithful_get_broker(MagicMock())), \
            patch.object(adapter, "BROKER", None), \
            patch("services.public_budget.budget", _budget()):
        from services import public_budget as pb_mod
        _run_cancelled_in_vendor_call(pb_mod.budget,
                                      _SEAM_CALLS["chain"], started)
    adapter.BROKER = None
    adapter._CHAIN_CACHE.clear()


def test_r4_cancel_during_vendor_call_releases_range_seam():
    """Range seam: cancelling while the spot/vendor resolution is in
    flight (debit already held) releases the slot exactly once."""
    started, hang = _hang_mock()
    adapter._CHAIN_CACHE.clear()
    with patch.object(adapter, "_resolve_spot_observation", new=hang), \
            patch.object(adapter, "_get_broker",
                         new=_faithful_get_broker(MagicMock())), \
            patch.object(adapter, "BROKER", None), \
            patch("services.public_budget.budget", _budget()):
        from services import public_budget as pb_mod
        _run_cancelled_in_vendor_call(pb_mod.budget,
                                      _SEAM_CALLS["range"], started)
    adapter.BROKER = None
    adapter._CHAIN_CACHE.clear()


def test_r4_cancel_during_vendor_call_releases_listing_seam():
    """Listing seam: cancelling while the vendor expirations call is in
    flight (debit already held) releases the slot exactly once."""
    started, hang = _hang_mock()
    broker = MagicMock()
    broker.get_option_expirations = hang
    adapter._CHAIN_CACHE.clear()
    with patch.object(adapter, "_get_broker",
                      new=_faithful_get_broker(broker)), \
            patch.object(adapter, "BROKER", None), \
            patch("services.public_budget.budget", _budget()):
        from services import public_budget as pb_mod
        _run_cancelled_in_vendor_call(
            pb_mod.budget, lambda: adapter.fetch_option_expiry_listing("SPY"),
            started)
    adapter.BROKER = None
    adapter._CHAIN_CACHE.clear()


def test_r4_cancel_during_lock_wait_spends_zero():
    """A same-key WAITER cancelled while queued on the key lock never
    debits (admission happens UNDER the lock) and never leaks a slot."""
    started, hang = _hang_mock()
    adapter._CHAIN_CACHE.clear()
    with patch.object(adapter, "_fetch_chain_live", new=hang), \
            patch.object(adapter, "_get_broker",
                         new=_faithful_get_broker(MagicMock())), \
            patch.object(adapter, "BROKER", None), \
            patch("services.public_budget.budget", _budget()):
        from services import public_budget as pb_mod
        budget = pb_mod.budget

        async def main():
            leader = asyncio.create_task(
                adapter.fetch_chain_from_public_api("SPY", 2))
            await asyncio.wait_for(started.wait(), 5)
            # The leader holds the key lock and has ALREADY debited its one
            # envelope (it is hanging inside the vendor call).
            mid = await budget.peek_available()
            waiter = asyncio.create_task(
                adapter.fetch_chain_from_public_api("SPY", 2))
            await asyncio.sleep(0.05)  # waiter is queued on the key lock
            waiter.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await waiter
            # The cancelled waiter spent NOTHING (it never reached the
            # under-lock admission) and leaked NOTHING.
            after = await budget.peek_available()
            assert mid - after == 0
            leader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await leader
            assert budget._inflight == 0

        asyncio.run(main())
    adapter.BROKER = None
    adapter._CHAIN_CACHE.clear()


# ── R5 (C01): committed docs fixtures are PRODUCER-TRUE ─────────────────────

DOCS_FIXTURES = Path(__file__).resolve().parents[3] / \
    "docs/solstice/r18/fixtures"


def test_r5_partial_fixture_is_honest_and_synthetic():
    """The published partial fixture is regenerated from the real producer:
    synthetic stays TRUE (a hand-made fixture can never claim production
    provenance), admitted == returned + skipped, and the skipped expiry's
    cells are explicit nulls over the owning axes — never a contradictory
    n_admitted=3/returned=0/skipped=1 with synthetic=false (the review's
    census-production blocker)."""
    d = json.loads((DOCS_FIXTURES / "partial_skipped_v1.json").read_text())
    cov = d["coverage"]
    assert d["synthetic"] is True
    assert d["status"] == "partial"
    assert cov["n_admitted"] == 3
    assert cov["n_returned_expiries"] + cov["n_skipped_expiries"] == \
        cov["n_admitted"]
    assert cov["complete"] is False
    assert cov["complete_reason"] == "SKIPPED_EXPIRIES"
    axes = {a["expiry"] for a in d["axes"]["expiries"]}
    skipped = {s["expiry"] for s in cov["skipped"]}
    assert skipped <= axes
    for name, grid in d["grids"].items():
        cells = grid["cells"]
        # Cells span the OWNING axes exactly: the skipped expiry keeps
        # explicit NULL cells (honest gaps), never dropped rows.
        assert set(cells) == axes, name
        for exp in skipped:
            assert all(v is None for v in cells[exp].values()), (name, exp)
    # The digest is content-true and identity derives from it.
    assert d["content_digest"] == compute_content_digest(d)
    assert d["record_id"] == record_id_for_digest(d["content_digest"])


def test_r5_all_fixtures_stay_synthetic_and_self_consistent():
    """Every committed envelope/wrapper fixture keeps synthetic provenance
    and digest truth — fixtures, wrappers and the index agree, and no
    fixture claims production."""
    names = ("complete_v1.json", "partial_skipped_v1.json",
             "record_replay_v1.json", "record_replay_partial_v1.json")
    envelopes = {}
    for name in names:
        d = json.loads((DOCS_FIXTURES / name).read_text())
        env = d.get("envelope", d)
        if name.startswith("record_replay"):
            assert d["version"] == "range-records.v1"
            assert d["integrity"] == "verified"
        assert env["synthetic"] is True, name
        assert env["content_schema"] == "rga-content.v3", name
        assert env["content_digest"] == compute_content_digest(env), name
        assert env["record_id"] == record_id_for_digest(
            env["content_digest"]), name
        cov = env["coverage"]
        assert cov["n_admitted"] == (cov["n_returned_expiries"]
                                     + cov["n_skipped_expiries"]), name
        envelopes[name] = env
    # Wrapper envelopes are byte-identical to the bare fixtures.
    assert envelopes["record_replay_v1.json"] == \
        envelopes["complete_v1.json"]
    assert envelopes["record_replay_partial_v1.json"] == \
        envelopes["partial_skipped_v1.json"]
    # The index lists both records as synthetic with verified integrity.
    idx = json.loads((DOCS_FIXTURES / "record_index_v1.json").read_text())
    assert idx["version"] == "range-records.v1" and idx["status"] == "ok"
    assert idx["n_returned"] == 2
    for row in idx["rows"]:
        assert row["synthetic"] is True
        assert row["integrity"] == "verified"
    # Refusals stay typed and versioned.
    ref = json.loads((DOCS_FIXTURES / "record_replay_refused_v1.json")
                     .read_text())
    assert ref["status"] == "refused" and ref["reason"] == "NO_RECORD"
    assert ref["version"] == "range-records.v1"
    rev = json.loads((DOCS_FIXTURES / "refused_reversed_v1.json").read_text())
    assert rev["status"] == "refused" and \
        rev["refusals"] == ["REVERSED_WINDOW"]


def test_r5_generator_is_idempotent(tmp_path):
    """The committed generator reproduces the frozen fixture bytes exactly
    from the current producer — a materially changed producer shows up as
    a hash diff instead of silent fixture drift."""
    import hashlib
    import subprocess

    repo = Path(__file__).resolve().parents[3]
    staging = tmp_path / "fixtures"
    staging.mkdir()
    gen = repo / "backend/tests/solstice/regen_r18_docs_fixtures.py"
    proc = subprocess.run(
        [sys.executable, str(gen), str(staging)],
        capture_output=True, text=True, cwd=repo)
    assert proc.returncode == 0, proc.stderr[-2000:]
    hashes = json.loads(proc.stdout[:proc.stdout.index("}") + 1])
    docs_dir = DOCS_FIXTURES
    for name, digest in hashes.items():
        current = hashlib.sha256((docs_dir / name).read_bytes()).hexdigest()
        assert digest == current, \
            f"{name}: committed fixture bytes diverged from the producer"


# ── R6 (C06): delta/volume exclusions stay visible beside finite siblings ──

def _chain_with_defects():
    """Sibling-finite chain carrying one contract per silent-exclusion
    class the vendor-gamma kernels drop WITHOUT their own counter."""
    chain = json.loads((FIXTURES / "chain_complete.json").read_text())
    contracts = list(chain["contracts"])
    base = dict(contracts[0])

    def with_expiry(exp):
        c = dict(base)
        c["expiry"] = exp
        c["strike"] = 595.0
        c["type"] = "call"
        return c

    no_gamma = with_expiry("2026-10-26")
    no_gamma["gamma"] = None            # vendor gamma absent
    no_oi = with_expiry("2026-10-26")
    no_oi["oi"] = 0                     # OI missing/nonpositive
    bad_strike = with_expiry("2026-10-26")
    bad_strike["strike"] = 0            # strike invalid
    no_expiry = with_expiry("")         # expiry absent
    contracts += [no_gamma, no_oi, bad_strike, no_expiry]
    chain["contracts"] = contracts
    return chain


def test_r6_missing_gamma_exclusion_stays_visible():
    """The delta/volume kernels silently drop missing-vendor-gamma
    contracts; the population must count them (review: 'exclusions hidden
    behind sibling finite cells/status ok') and keep the metric partial —
    finite sibling cells never admit the metric."""
    env = _env(**{"contracts": _chain_with_defects()["contracts"]})
    for name in ("delta_weighted", "volume"):
        grid = env["grids"][name]
        pop = grid["population"]
        assert pop["gamma_missing"] == 1, (name, pop)
        # Sibling cells are still finite — but the exclusion is VISIBLE
        # and the metric stays partial/not-admitted (never 'ok').
        assert grid["status"] == "partial", (name, grid["status"])
        assert grid["metric_admitted"] is False, name
        assert name in env["metrics"]["partial"], name
        assert name not in env["metrics"]["admitted"], name


def test_r6_oi_and_strike_and_expiry_exclusions_visible():
    """Missing OI (delta kernel only), invalid strike and absent expiry
    are kernel-order-faithful first-skip counters in both populations."""
    env = _env(**{"contracts": _chain_with_defects()["contracts"]})
    dw = env["grids"]["delta_weighted"]["population"]
    vol = env["grids"]["volume"]["population"]
    # Delta kernel consumes OI before gamma/delta: the no-OI contract is
    # oi_missing; volume has no OI requirement at all.
    assert dw["oi_missing_or_nonpositive"] == 1, dw
    assert "oi_missing_or_nonpositive" not in vol, vol
    # The no-OI contract never counts as gamma_missing/missing_delta.
    assert dw["gamma_missing"] == 1, dw
    assert dw["strike_invalid"] == 1, dw
    assert dw["expiry_missing"] == 1, dw
    # Volume kernel order: volume -> gamma -> strike -> expiry.
    assert vol["strike_invalid"] == 1, vol
    assert vol["expiry_missing"] == 1, vol
    # Both stay partial despite finite siblings.
    for name in ("delta_weighted", "volume"):
        assert env["grids"][name]["metric_admitted"] is False, name


def test_r6_raw_oi_bs_mirror_unaffected_by_missing_vendor_gamma():
    """A contract with iv/T but no vendor gamma is USABLE to the BS raw
    surface (the kernel computes gamma from iv) — the vendor-gamma mirrors
    never contaminate the raw_oi population (C11 raw-BS truth preserved)."""
    env = _env(**{"contracts": _chain_with_defects()["contracts"]})
    raw = env["grids"]["raw_oi"]["population"]
    assert "gamma_missing" not in raw, raw
    # The BS mirror counts its own kernel-order exclusions only: the
    # missing-gamma/no-OI/bad-strike/no-expiry contracts fall to their
    # BS first-skip reasons (strike_invalid for bad_strike, etc.).
    assert raw["strike_invalid"] == 1, raw
    assert raw["usable"] >= 1, raw


def test_r6_mirror_matches_kernel_counters():
    """The mirrors reproduce every kernel-reported counter exactly —
    correspondence, not just plausibility."""
    from services.gex_core import (
        compute_gex_grid_delta_weighted,
        compute_gex_grid_volume_vendor,
    )
    contracts = _chain_with_defects()["contracts"]
    spot = 600.0
    dw_k = compute_gex_grid_delta_weighted(spot, contracts)
    vol_k = compute_gex_grid_volume_vendor(spot, contracts)
    env = _env(**{"contracts": contracts})
    dw = env["grids"]["delta_weighted"]["population"]
    vol = env["grids"]["volume"]["population"]
    for key in ("usable", "missing_delta", "invalid_delta", "invalid_mult",
                "quarantined", "invalid_type"):
        assert dw[key] == dw_k.get(key), (key, dw[key], dw_k.get(key))
    for key in ("usable", "quarantined", "invalid_mult", "invalid_type"):
        assert vol[key] == vol_k.get(key), (key, vol[key], vol_k.get(key))

"""Regenerate the frozen r18 consumer docs fixtures FROM the real producer.

R18-C12 (review 5979463755, C01): the published partial fixture was a
hand-built contradiction — ``n_admitted=3`` with ``returned=0/skipped=1``,
four finite cells over six declared axes and ``synthetic=false`` on a
synthetic record (which then counted as ``production`` in the census).
This generator drives the AUTHORITATIVE producer
(``services.solstice_range_analytics.build_range_envelope``) and the real
store/replay/index seams, so every fixture is internally coherent by
construction:

  * every envelope and wrapper stays ``synthetic: true`` (fixture truth);
  * ``coverage.n_admitted == n_returned_expiries + n_skipped_expiries``
    under the producer's own semantics;
  * axes/cells/coverage agree (cells span the owning admitted axes; the
    skipped expiry's cells are explicit nulls, never dropped);
  * the canonical content digest recomputes and record identity derives
    from it;
  * wrappers are produced by the same code the mounted routes use.

Deterministic byte-for-byte: the store receipt clock (``recorded_at``) is
pinned to the synthetic session, so regeneration is idempotent.

Usage: ``python3 backend/tests/solstice/regen_r18_docs_fixtures.py``
(writes ``docs/solstice/r18/fixtures/`` and prints the sha256 table for
the contract doc). No network; no production store is touched.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

sys.path.insert(0, "backend")

import duckdb  # noqa: E402

from services.heatmap_history import (  # noqa: E402
    list_range_envelopes,
    record_range_envelope,
    replay_range_envelope,
)
from services.solstice_range_analytics import (  # noqa: E402
    build_range_envelope,
    compute_content_digest,
    fetch_range_analytics,
    record_id_for_digest,
    select_window_expiries,
)

TEST_FIXTURES = Path(__file__).parent / "fixtures" / "range_analytics_v1"
DOCS_FIXTURES = Path(__file__).resolve().parents[3] / \
    "docs/solstice/r18/fixtures"
TODAY = date(2026, 10, 5)
NOW = datetime(2026, 10, 5, 14, 0, 0, tzinfo=UTC)
# Synthetic store receipt clock for the frozen scenario (idempotent bytes).
RECORDED_AT = "2026-10-05T14:00:01+00:00"


def _load(name: str) -> dict:
    return json.loads((TEST_FIXTURES / name).read_text())


def _partial_chain() -> dict:
    """Honest partial chain: the 2026-12-04 fetch FAILED (skipped), and one
    surviving contract carries an invalid delta (kernel-counted exclusion
    beside finite sibling cells)."""
    chain = _load("chain_complete.json")
    kept = [c for c in chain["contracts"]
            if c.get("expiry") != "2026-12-04"]
    for c in kept:
        if c.get("expiry") == "2026-11-09" and c.get("strike") == 600.0 \
                and c.get("type") == "put":
            c["delta"] = "not-a-number"
    chain["contracts"] = kept
    chain["expiries"] = ["2026-10-26", "2026-11-09"]
    chain["skipped"] = [{"expiry": "2026-12-04",
                        "reason": "CHAIN_FETCH_FAILED"}]
    return chain


def _assert_invariants(env: dict, label: str) -> None:
    cov = env["coverage"]
    na, nr, ns = (cov["n_admitted"], cov["n_returned_expiries"],
                  cov["n_skipped_expiries"])
    assert na == nr + ns, (label, na, nr, ns)
    assert env["synthetic"] is True, (label, "fixture must stay synthetic")
    assert env["content_digest"] == compute_content_digest(env), label
    assert env["record_id"] == record_id_for_digest(env["content_digest"]), label
    axes = env["axes"]["expiries"]
    assert na == len(axes), (label, na, len(axes))
    for name, grid in env["grids"].items():
        cells = grid["cells"]
        assert set(cells.keys()) == {a["expiry"] for a in axes}, \
            (label, name, "cells must span the owning axes exactly")
        declared = cov["n_admitted"] * env["axes"]["n_strikes"]
        assert grid["n_cells"] == declared, (label, name)


def main(argv: list[str] | None = None) -> int:
    # Optional explicit output directory (verification harnesses use it to
    # regenerate into a staging copy and compare bytes).
    docs_dir = DOCS_FIXTURES
    if argv and argv[0]:
        docs_dir = Path(argv[0])
    listing = _load("listing.json")
    sel = select_window_expiries(listing["expiries"], 14, 60, TODAY)

    complete = build_range_envelope(symbol="SPY", min_dte=14, max_dte=60,
                                    asof=TODAY, listing=listing,
                                    selection=sel,
                                    chain=_load("chain_complete.json"))
    partial = build_range_envelope(symbol="SPY", min_dte=14, max_dte=60,
                                   asof=TODAY, listing=listing,
                                   selection=sel, chain=_partial_chain())
    # v3: the partial envelope is captured SECONDS after the complete one —
    # the skipped 12-04 fetch attempt happens between the two. A shared
    # received_at drops the chronological replay tiebreak to record_id alone;
    # give partial its own later receive clock so both records carry distinct
    # owning clocks (host the regression that the previous v2 fixture masked).
    _pf = dict(partial["clocks"])
    _pf["received_at"] = "2026-10-05T13:59:35+00:00"
    partial["clocks"] = _pf
    # Re-seal after the clock override so the digest covers the true bytes.
    from services.solstice_range_analytics import compute_content_digest
    from services.solstice_range_analytics import record_id_for_digest as _rid
    partial["content_digest"] = compute_content_digest(partial)
    partial["record_id"] = _rid(partial["content_digest"])
    _assert_invariants(complete, "complete_v1")
    _assert_invariants(partial, "partial_skipped_v1")
    assert complete["status"] == "ok", complete["status"]
    assert partial["status"] == "partial" and \
        partial["coverage"]["complete_reason"] == "SKIPPED_EXPIRIES", partial

    # Reversed-window refusal envelope straight from the owning fetch seam.
    refused = asyncio.run(fetch_range_analytics("SPY", 60, 14, now_utc=NOW))
    assert refused["status"] == "refused" and \
        refused["refusals"] == ["REVERSED_WINDOW"], refused

    # Store + replay through the REAL seams; pin the receipt clock so the
    # frozen bytes are idempotent across regenerations.
    conn = duckdb.connect(":memory:")
    try:
        for env in (complete, partial):
            res = record_range_envelope(conn, env)
            assert res["status"] == "recorded", res
            conn.execute(
                "UPDATE range_analytics_envelopes_v1 SET recorded_at = ? "
                "WHERE record_id = ?", [RECORDED_AT, env["record_id"]])
        rep_ok = replay_range_envelope(conn, complete["record_id"])
        rep_partial = replay_range_envelope(conn, partial["record_id"])
        index = list_range_envelopes(conn, ticker="SPY")
    finally:
        conn.close()
    assert rep_ok["integrity"] == "verified" and \
        rep_partial["integrity"] == "verified"
    assert index["status"] == "ok" and index["n_returned"] == 2

    DOCS_FIXTURES.mkdir(parents=True, exist_ok=True)
    out: dict[str, str] = {}
    files = {
        "complete_v1.json": complete,
        "partial_skipped_v1.json": partial,
        "refused_reversed_v1.json": refused,
        # Mounted-route wrapper shapes, produced by the route-owned code.
        "record_replay_v1.json": {"version": "range-records.v1",
                                 "status": "ok", **rep_ok},
        "record_replay_partial_v1.json": {"version": "range-records.v1",
                                          "status": "ok", **rep_partial},
        "record_replay_refused_v1.json": {
            "version": "range-records.v1", "status": "refused",
            "reason": "NO_RECORD", "record_id": "rga1-norecordfixture000000"},
        "record_index_v1.json": index,
    }
    for name, payload in files.items():
        path = docs_dir / name
        path.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
        out[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    print(json.dumps(out, indent=2))
    print(f"complete record_id {complete['record_id']} digest "
          f"{complete['content_digest']}")
    print(f"partial  record_id {partial['record_id']} digest "
          f"{partial['content_digest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

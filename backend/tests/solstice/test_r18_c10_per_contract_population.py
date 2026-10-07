"""C10: per-contract identity population persisted and restituted exactly.

OpenCode's independent review of the C10 acceptance at main 1fc5582c
(packet references/evidence/c10-1fc5582c-probe.log) returned PARTIAL with a
concrete counterexample: the sealed fixtures carry aggregate axes/metrics/
clocks and a per-contract identity DIGEST, but NO per-contract OSI/series/
expiry/strike/right/multiplier rows — so exact per-contract restitution from
the owning persisted population was UNPROVEN. The acceptance text requires
recovering exact OSI/series/expiry/strike/right/multiplier/quote-side clocks
from the owning persisted population with typed refusals and never
current-chain reconstruction.

These pins close that gap through the OWNING seams only
(``services.solstice_range_analytics.build_range_envelope`` producer ->
``services.heatmap_history.record_range_envelope`` ->
``replay_range_envelope`` resolver): rows join the digest-bound grounding
block, tamper is a typed refusal, replay restitutes byte-identically
offline, invalid multipliers rest null (R10-02), drafting stays
RANGE_RECORD_REFERENCE_ONLY, and the sealed fixture carries the population.

Deterministic; no network; throwaway :memory: DuckDB only.
"""
from __future__ import annotations

import copy
import json
import socket
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, "backend")

import duckdb

from services.agent.stored_contract_resolver import bind_stored_range_contract
from services.heatmap_history import (
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
DOCS_FIXTURES = Path(__file__).resolve().parents[3] / "docs/solstice/r18/fixtures"
TODAY = date(2026, 10, 5)


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _build(chain: dict | None = None) -> dict:
    chain = chain if chain is not None else _load("chain_complete.json")
    listing = _load("listing.json")
    sel = select_window_expiries(listing["expiries"], 14, 60, TODAY)
    return build_range_envelope(symbol="SPY", min_dte=14, max_dte=60,
                                asof=TODAY, listing=listing,
                                selection=sel, chain=chain)


def _expected_row(osi: str, expiry: str, strike_key: str, right: str) -> dict:
    return {"osi": osi, "series": "EQUITY", "expiry": expiry,
            "strike_key": strike_key, "right": right,
            "multiplier": 100.0, "multiplier_provenance": "EXPLICIT"}


def test_c10_grounding_persists_exact_per_contract_identity_rows():
    """The owning record carries the EXACT per-contract identity population
    (OSI/series/expiry/strike/right/multiplier), deterministically ordered —
    not just an aggregate digest of it."""
    env = _build()
    rows = env["grounding"]["contract_rows"]
    assert isinstance(rows, list) and len(rows) == 12

    def key(r):
        return (r["expiry"], r["strike_key"], r["right"], r["osi"])

    assert rows == sorted(rows, key=key)
    expected = [
        _expected_row(f"FAKE-{e}-{s}-{rt.upper()}", e, s, rt)
        for e in ("2026-10-26", "2026-11-09", "2026-12-04")
        for s in ("590", "600")
        for rt in ("call", "put")
    ]
    expected.sort(key=key)
    assert rows == expected

    # Identity population agrees with the per-expiry aggregate counts the
    # record already carried (same captured contracts, no phantom rows).
    per_expiry = env["grounding"]["contract_population"]
    for expiry, pop in per_expiry.items():
        mine = [r for r in rows if r["expiry"] == expiry]
        assert len(mine) == pop["n_contracts"], expiry
        assert sum(1 for r in mine if r["right"] == "call") == pop["n_call"]
        assert sum(1 for r in mine if r["right"] == "put") == pop["n_put"]


def test_c10_contract_rows_join_the_canonical_content_digest():
    """Rows live inside the digest subject: any per-contract identity
    mutation changes the canonical content digest (tamper-evident by
    construction, no new integrity mechanism needed)."""
    env = _build()
    tampered = copy.deepcopy(env)
    tampered["grounding"]["contract_rows"][0]["osi"] = "SPYW 99999999C99999999"
    assert compute_content_digest(tampered) != env["content_digest"]
    tampered2 = copy.deepcopy(env)
    tampered2["grounding"]["contract_rows"][0]["multiplier"] = 1000.0
    assert compute_content_digest(tampered2) != env["content_digest"]
    tampered3 = copy.deepcopy(env)
    tampered3["grounding"]["contract_rows"][0]["right"] = "put"
    assert compute_content_digest(tampered3) != env["content_digest"]


def test_c10_record_replay_round_trip_restitutes_rows_exactly():
    """Seeded through the owning write path and restituted byte-identically
    by the replay resolver — fully offline, never a current-chain fetch."""
    env = _build()
    rows = env["grounding"]["contract_rows"]
    conn = duckdb.connect(":memory:")
    try:
        with patch.object(socket, "create_connection",
                          side_effect=AssertionError("replay must be offline")):
            receipt = record_range_envelope(conn, env)
            assert receipt["status"] == "recorded", receipt
            rep = replay_range_envelope(conn, env["record_id"])
            assert rep is not None and rep["integrity"] == "verified", rep
    finally:
        conn.close()
    assert rep["envelope"]["grounding"]["contract_rows"] == rows
    assert rep["envelope"] == env  # exact stored envelope, byte-identical


def test_c10_stored_row_tamper_is_typed_refusal_never_served():
    """Tampering a stored per-contract identity row leaves the digest stale —
    replay must return a typed refusal and NEVER serve the payload; the
    duplicate-write check must refuse the mutated identity the same way."""
    env = _build()
    conn = duckdb.connect(":memory:")
    try:
        assert record_range_envelope(conn, env)["status"] == "recorded"
        rid = env["record_id"]
        stored = conn.execute(
            "SELECT envelope_json FROM range_analytics_envelopes_v1 "
            "WHERE record_id = ?", [rid]).fetchone()[0]
        payload = json.loads(stored)
        payload["grounding"]["contract_rows"][0]["osi"] = "SPY 2501020C00500000"
        conn.execute(
            "UPDATE range_analytics_envelopes_v1 SET envelope_json = ? "
            "WHERE record_id = ?", [json.dumps(payload), rid])
        rep = replay_range_envelope(conn, rid)
        assert rep["envelope"] is None and rep["error"] == "DIGEST_MISMATCH", rep
        # The duplicate-write path recomputes the digest from the payload, so
        # the mutated population cannot re-enter under the stale claimed
        # digest (typed DIGEST_MISMATCH at the write seam) — and a fully
        # self-consistent forgery carrying its OWN digest/record_id can
        # never serve under the original row's identity either.
        dup = record_range_envelope(conn, payload)
        assert dup["status"] == "refused" and dup["reason"] == "DIGEST_MISMATCH"
        forged = copy.deepcopy(payload)
        forged["content_digest"] = compute_content_digest(forged)
        forged["record_id"] = record_id_for_digest(forged["content_digest"])
        assert record_range_envelope(conn, forged)["status"] == "recorded"
        # Identity swap: the self-consistent forgery parked under the ORIGINAL
        # row's id cannot serve — the binder binds row id to payload id.
        conn.execute(
            "UPDATE range_analytics_envelopes_v1 SET envelope_json = ? "
            "WHERE record_id = ?", [json.dumps(forged), rid])
        swap = replay_range_envelope(conn, rid)
        assert swap["envelope"] is None and swap["error"] == "ROW_HEADER_MISMATCH", swap
    finally:
        conn.close()


def test_c10_drafting_stays_reference_only_with_rows_present():
    """The per-contract population is REFERENCE IDENTITY ONLY: rows never
    flip drafting to admitted, and the Lodestar stored-contract binding seam
    keeps surfacing RANGE_RECORD_REFERENCE_ONLY while verifying the record."""
    env = _build()
    assert env["grounding"]["contract_rows"]
    assert env["grounding"]["contract_drafting"] == {
        "admitted": False, "reason": "RANGE_RECORD_REFERENCE_ONLY"}
    bound = bind_stored_range_contract({
        "rangeRecordId": env["record_id"],
        "rangeMetric": "raw_oi",
        "rangeDigest": env["content_digest"],
        "stored_envelope": env,
    })
    assert bound["verified"] is True and bound["grounded"] is True, bound
    assert bound["blocker"] == "RANGE_RECORD_REFERENCE_ONLY", bound
    assert bound["query_identity"] == {
        "symbol": "SPY", "min_dte": 14, "max_dte": 60,
        "as_of_ny": "2026-10-05"}


def test_c10_invalid_multiplier_identity_rests_null_never_defaulted():
    """R10-02 at the identity layer: an explicitly invalid multiplier rests
    null with its typed provenance — never a fabricated 100 — while an
    absent multiplier carries the documented standard default honestly."""
    chain = _load("chain_complete.json")
    chain["contracts"][0]["multiplier"] = "not-a-number"
    chain["contracts"][1].pop("multiplier")
    env = _build(chain)
    rows = env["grounding"]["contract_rows"]
    by_osi = {r["osi"]: r for r in rows}
    invalid = by_osi["FAKE-2026-10-26-590-CALL"]
    assert invalid["multiplier"] is None
    assert invalid["multiplier_provenance"] == "MULTIPLIER_INVALID"
    defaulted = by_osi["FAKE-2026-10-26-590-PUT"]
    assert defaulted["multiplier"] == 100.0
    assert defaulted["multiplier_provenance"] == "DEFAULT_STANDARD"
    # The kernel-side exclusion stays visible beside the identity rows
    # (population honesty: the invalid contract is still counted invalid).
    assert any(sec.get("invalid_mult") for sec in env["grids"].values())


def test_c10_sealed_replay_fixture_carries_per_contract_population():
    """The committed sealed carrier now demonstrates what the C10 probe
    withheld: a stored record whose replay restitutes a real per-contract
    OSI/series/expiry/strike/right/multiplier population, self-consistent
    under the recomputed canonical digest."""
    d = json.loads((DOCS_FIXTURES / "record_replay_v1.json").read_text())
    env = d["envelope"]
    rows = env["grounding"]["contract_rows"]
    assert rows and len(rows) == 12
    assert all(r["osi"] and r["series"] and r["expiry"] and
               r["strike_key"] and r["right"] and
               r["multiplier"] is not None for r in rows)
    assert compute_content_digest(env) == env["content_digest"]
    # Index identity agrees with the sealed carrier.
    idx = json.loads((DOCS_FIXTURES / "record_index_v1.json").read_text())
    row = next(r for r in idx["rows"] if r["record_id"] == env["record_id"])
    assert row["digest"] == env["content_digest"]



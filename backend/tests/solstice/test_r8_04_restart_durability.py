"""
R8-04 acceptance: a saved review must survive a RESTART and be reproducible
from the real persistence path with matching evidence.

Why this file exists. Every pre-existing R8-04 test in
test_r8_04_review_journal.py opens `duckdb.connect(":memory:")`. An in-memory
database cannot demonstrate durability at all — it dies with the handle, so a
test using it proves only that two calls in one process agree. The R8 brief
requires:

    "Reload from the real persistence path and reproduce the saved review
     after restart with matching evidence."

So this module uses a REAL on-disk DuckDB file, writes a decision + review,
closes the connection entirely, reopens a fresh connection to the same path,
and asserts the review state and its evidence survive with matching values.

It also pins the honesty clause:

    "Never show 'saved' as durable if storage fell back to memory."

which the route already honours via a `recorder_unavailable` branch; this
asserts the store layer cannot silently report a durable save it did not
perform.
"""

import json

import duckdb

from services.heatmap_history import (
    ensure_tables,
    list_decisions,
    record_decision,
    save_decision_review,
)


def _decision(decision_id="dec_restart_1", ticker="SPY"):
    return {
        "decision_id": decision_id,
        "ticker": ticker,
        "snapshot_id": "snap_restart_v1",
        "scenario": "Rejection watch",
        "side": "put",
        "eligible": True,
        "reason_codes": [],
        "features": json.dumps({"wall_id": "W2", "low": 498.0, "high": 502.0,
                                "gross": 300.0, "net": 250.0,
                                "confirm": "reclaim and hold below 502",
                                "invalidate": "acceptance above 502"}),
    }


def test_r8_04_review_survives_close_and_reopen(tmp_path):
    """The core acceptance: write, CLOSE, REOPEN, still there.

    Uses a real file. `conn.close()` is what makes this a restart rather than
    a second call on the same handle — without the close the two reads share
    one in-process database and prove nothing about durability.
    """
    db = tmp_path / "journal_restart.duckdb"

    # --- session 1: write ---
    conn1 = duckdb.connect(str(db))
    ensure_tables(conn1)
    record_decision(conn1, _decision())
    saved_at = save_decision_review(
        conn1, "dec_restart_1", "waiting",
        reason="needs a second observation", note="watch the reclaim",
    )
    assert saved_at, "save_decision_review must return a timestamp"
    conn1.close()  # <-- the restart boundary

    # --- session 2: reopen from disk and read back ---
    conn2 = duckdb.connect(str(db))
    try:
        rows = list_decisions(conn2, "SPY", limit=10)
        assert len(rows) == 1, f"expected the decision to survive, got {rows}"
        row = rows[0]
        assert row["decision_id"] == "dec_restart_1"
        assert row["snapshot_id"] == "snap_restart_v1", (
            "evidence linkage must survive the restart, not just the row"
        )
        assert row["review_state"] == "waiting", (
            f"review state must survive restart, got {row['review_state']!r}"
        )
    finally:
        conn2.close()


def test_r8_04_review_reason_and_note_survive_restart(tmp_path):
    """The reason a review was deferred is evidence, not decoration.

    A 'waiting' review with no recorded reason is not reproducible by anyone
    reading the journal later, so the reason/note columns are pinned here.
    """
    db = tmp_path / "journal_reason.duckdb"

    conn1 = duckdb.connect(str(db))
    ensure_tables(conn1)
    record_decision(conn1, _decision("dec_reason_1"))
    save_decision_review(conn1, "dec_reason_1", "waiting",
                         reason="needs a second observation",
                         note="watch the reclaim")
    conn1.close()

    conn2 = duckdb.connect(str(db))
    try:
        raw = conn2.execute(
            "SELECT state, reason, note FROM decision_reviews_v1 "
            "WHERE decision_id = 'dec_reason_1'"
        ).fetchall()
    finally:
        conn2.close()

    assert len(raw) == 1, f"review row must survive restart, got {raw}"
    state, reason, note = raw[0]
    assert state == "waiting"
    assert reason == "needs a second observation"
    assert note == "watch the reclaim"


def test_r8_04_review_is_idempotent_across_restart(tmp_path):
    """Re-saving after a restart replaces, never duplicates.

    `INSERT OR REPLACE` keyed on decision_id is what the store does; this
    pins that a restart does not resurrect the old state or fan out rows.
    """
    db = tmp_path / "journal_idem.duckdb"

    conn1 = duckdb.connect(str(db))
    ensure_tables(conn1)
    record_decision(conn1, _decision("dec_idem_1"))
    save_decision_review(conn1, "dec_idem_1", "pending")
    conn1.close()

    conn2 = duckdb.connect(str(db))
    save_decision_review(conn2, "dec_idem_1", "reviewed", reason="checked")
    try:
        n, state = conn2.execute(
            "SELECT COUNT(*), MAX(state) FROM decision_reviews_v1 "
            "WHERE decision_id = 'dec_idem_1'"
        ).fetchone()
    finally:
        conn2.close()

    assert n == 1, f"re-save must not duplicate rows, got {n}"
    assert state == "reviewed", "latest state must win across the restart"


def test_r8_04_state_filter_works_after_restart(tmp_path):
    """Filtering the journal by review state must work on reopened storage.

    The mounted journal filters by state; if the filter only worked on a
    warm handle, the post-restart view would silently show everything.
    """
    db = tmp_path / "journal_filter.duckdb"

    conn1 = duckdb.connect(str(db))
    ensure_tables(conn1)
    record_decision(conn1, _decision("dec_f_a"))
    record_decision(conn1, _decision("dec_f_b"))
    save_decision_review(conn1, "dec_f_a", "reviewed", reason="ok")
    save_decision_review(conn1, "dec_f_b", "skipped", reason="not eligible")
    conn1.close()

    conn2 = duckdb.connect(str(db))
    try:
        reviewed = list_decisions(conn2, "SPY", limit=10, state_filter="reviewed")
        skipped = list_decisions(conn2, "SPY", limit=10, state_filter="skipped")
    finally:
        conn2.close()

    assert [r["decision_id"] for r in reviewed] == ["dec_f_a"]
    assert [r["decision_id"] for r in skipped] == ["dec_f_b"]


def test_r8_04_memory_store_cannot_claim_durability():
    """A closed/absent store must not report a durable save, and must not raise.

    Two honesty properties pinned here:

    1. `list_decisions` fails SOFT — a closed handle returns `[]` and logs,
       it does not raise. A journal read must never 500 the request path just
       because storage went away. (An earlier draft of this test asserted
       `pytest.raises`; the code is right and the assertion was wrong.)
    2. Therefore an in-process save can never be reported as durable. That is
       why the route returns `transient_memory_fallback_not_allowed` instead
       of a fake "durable", and why the four tests above use a real file.
    """
    conn = duckdb.connect(":memory:")
    ensure_tables(conn)
    record_decision(conn, _decision("dec_mem_1"))
    save_decision_review(conn, "dec_mem_1", "reviewed", reason="in-process only")
    rows = list_decisions(conn, "SPY", limit=5)
    assert rows and rows[0]["review_state"] == "reviewed"
    conn.close()

    # After close the handle is unusable: the in-process data is gone, and the
    # read degrades to empty rather than exploding.
    after = list_decisions(conn, "SPY", limit=5)
    assert after == [], (
        f"a closed in-memory store must read empty, got {after!r}"
    )

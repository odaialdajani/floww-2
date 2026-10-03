"""R18-C2: TRUE independent-process persistence/replay proof (synthetic data).

The legacy reopen test (test_r15_price_producer.py:301-342) uses two
sequential connections in ONE Python process — preserved and unaffected. This
test proves actual process-restart durability of the OWNING range-analytics.v1
envelope plus price-path sequence:

  1. An independent WRITER process persists an explicitly synthetic full
     owning envelope + price path to an isolated FILE-backed store, exits 0.
  2. An independent READER process opens the same file (read_only) and
     restores the envelope identity, axes, cells, clocks and path sequence.
  3. PIDs differ; digests/identity/axes/cells/clocks match exactly.
  4. Missing/corrupt/schema cases stay explicit — nothing is fabricated.

DuckDB allows ONE writer process; this is sequential writer→reader restart
durability, NOT simultaneous multi-writer safety (Spark proves execution
exclusion separately). Production commissioning still requires approved real
records — this is the synthetic engineering proof only.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "backend")

import duckdb

from services.heatmap_history import ensure_range_tables, record_range_envelope, replay_range_envelope

REPO = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).parent / "fixtures" / "range_analytics_v1"

_WRITER = r"""
import json, os, sys
from datetime import date
from pathlib import Path
import duckdb
from services.heatmap_history import record_price_path, record_range_envelope
from services.solstice_range_analytics import (build_range_envelope,
                                               select_window_expiries)
db_path, fixtures, out = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
listing = json.loads((fixtures / "listing.json").read_text())
chain = json.loads((fixtures / "chain_complete.json").read_text())
sel = select_window_expiries(listing["expiries"], 14, 60, date(2026, 10, 5))
env = build_range_envelope(symbol="SPY", min_dte=14, max_dte=60,
                           asof=date(2026, 10, 5), listing=listing,
                           selection=sel, chain=chain)
conn = duckdb.connect(db_path)
res = record_range_envelope(conn, env)
for i in range(5):
    assert record_price_path(conn, "SPY", 1796431200.0 + 300.0 * i,
                             600.0 + 0.5 * i, "synthetic-fixture")
conn.close()
json.dump({"pid": os.getpid(), "record": res, "digest": env["content_digest"],
           "record_id": env["record_id"], "axes": env["axes"],
           "clocks": env["clocks"],
           "raw_cells": env["grids"]["raw_oi"]["cells"]},
          open(out, "w"))
print("writer ok")
"""

_READER = r"""
import json, os, sys
import duckdb
from services.heatmap_history import (price_paths_since,
                                      replay_range_envelope)
db_path, record_id, out = sys.argv[1], sys.argv[2], sys.argv[3]
conn = duckdb.connect(db_path, read_only=True)
rep = replay_range_envelope(conn, record_id)
paths = price_paths_since(conn, "SPY", 0.0)
conn.close()
json.dump({"pid": os.getpid(), "replay": rep, "paths": paths}, open(out, "w"))
print("reader ok")
"""


def _run(script: str, *args: str, env_extra: dict | None = None):
    env = dict(os.environ, PYTHONPATH=str(REPO / "backend"),
               **(env_extra or {}))
    # NB: no -I (isolated) flag — it ignores PYTHONPATH, which is exactly the
    # mechanism locating backend/ inside this worktree for the subprocess.
    return subprocess.run([sys.executable, "-c", script, *args],
                          capture_output=True, text=True, env=env, timeout=120)


def test_independent_process_replay_roundtrip(tmp_path):
    db = tmp_path / "range_proof.duckdb"
    w_out = tmp_path / "writer.json"
    r_out = tmp_path / "reader.json"

    writer = _run(_WRITER, str(db), str(FIXTURES), str(w_out))
    assert writer.returncode == 0, writer.stderr
    w = json.loads(w_out.read_text())
    assert w["record"]["status"] == "recorded"

    reader = _run(_READER, str(db), w["record_id"], str(r_out))
    assert reader.returncode == 0, reader.stderr
    r = json.loads(r_out.read_text())

    # Genuinely independent processes.
    assert w["pid"] != r["pid"] and os.getpid() not in (w["pid"], r["pid"])
    rep = r["replay"]
    # Identity, axes, cells, clocks and digest restore EXACTLY (no recompute).
    assert rep["digest"] == w["digest"]
    assert rep["envelope"]["record_id"] == w["record_id"]
    assert rep["envelope"]["axes"] == w["axes"]
    assert rep["envelope"]["clocks"] == w["clocks"]
    assert rep["envelope"]["grids"]["raw_oi"]["cells"] == w["raw_cells"]
    assert rep["envelope"]["synthetic"] is True
    assert rep["replay_note"].startswith("exact stored envelope")
    # Price-path sequence survives the process restart, order intact.
    assert [t for t, _ in r["paths"]] == [1796431200.0 + 300.0 * i for i in range(5)]


def test_missing_schema_and_corrupt_rows_stay_explicit(tmp_path):
    # Missing record in a store that has the table → None (unknown identity).
    db = tmp_path / "has_table.duckdb"
    conn = duckdb.connect(str(db))
    ensure_range_tables(conn)
    assert replay_range_envelope(conn, "rga1-nonexistent") is None
    # Corrupt payload → explicit CORRUPT_PAYLOAD, never a fabricated map.
    good = {"version": "range-analytics.v1", "status": "ok", "symbol": "SPY",
            "record_id": "rga1-corrupt", "content_digest": "d" * 64,
            "query": {"min_dte": 14, "max_dte": 60, "as_of_ny": "2026-10-05"},
            "axes": {}, "grids": {}, "metric_registry": {},
            "clocks": {"received_at": "2026-10-05T13:59:30+00:00"},
            "coverage": {}, "provenance": {}}
    assert record_range_envelope(conn, good)["status"] == "recorded"
    conn.execute("UPDATE range_analytics_envelopes_v1 SET envelope_json = '{bad' "
                 "WHERE record_id = 'rga1-corrupt'")
    corrupted = replay_range_envelope(conn, "rga1-corrupt")
    conn.close()
    assert corrupted["error"] == "CORRUPT_PAYLOAD"
    assert corrupted["envelope"] is None

    # A store WITHOUT the range table (legacy schema) → explicit read failure,
    # not a swallowed exception.
    legacy = tmp_path / "legacy.duckdb"
    conn2 = duckdb.connect(str(legacy))
    conn2.execute("CREATE TABLE legacy_only (id VARCHAR)")
    result = replay_range_envelope(conn2, "rga1-anything")
    conn2.close()
    assert result is not None and result["error"] == "STORE_READ_FAILED"


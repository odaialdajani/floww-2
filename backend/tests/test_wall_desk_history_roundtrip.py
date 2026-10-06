"""WallDeskSnapshot.v1 history round-trip: packet -> existing recorder -> replay.

Hermes-lease-safe by construction: this test only calls the existing
``record_snapshot``/``replay_snapshot`` API with the frozen packet. It does
not alter schema, routes, server wiring, or historical rows. Missing delta
and stale-quote labels must survive the round trip; replay must not invent
a smooth curve or fabricate intraday OI changes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domain.wall_desk_snapshot import project_packet  # noqa: E402
from tests.fixtures.wall_desk_fixture_v1 import (  # noqa: E402
    SOURCE_OBSERVATION_T0,
    SOURCE_OBSERVATION_T1,
)


def source_pair():
    return SOURCE_OBSERVATION_T0, SOURCE_OBSERVATION_T1


def test_packet_survives_record_replay_with_missingness_intact():
    duckdb = pytest.importorskip("duckdb")

    from services.heatmap_history import (  # noqa: E402
        ensure_tables,
        record_snapshot,
        replay_snapshot,
    )

    first, _ = source_pair()
    packet = project_packet(first, "fixture-t0")
    payload = {
        "ticker": packet["ticker"],
        "spot": packet["spot"],
        "asof": packet["asof"],
        "source_received_at": packet["source_received_at"],
        "data_source": packet["data_source"],
        "exposure_basis": "OI",
        "formula_version": packet["formula_version"],
        "expiries_used": packet["coverage"]["expiries"],
        "strikes": [],
        "grid": {},
        "contracts": first["contracts"],
        "metrics": {
            "walls": [{"wall_id": packet["wall_id"], "members": [100]}],
            "grids": {},
            "wall_desk_snapshot_v1": packet,
        },
        "coverage": {
            "requested": len(first["contracts"]),
            "returned": len(first["contracts"]),
            "usable": packet["raw_usable"],
            "truncated": False,
        },
    }

    conn = duckdb.connect(":memory:")
    ensure_tables(conn)
    sid = record_snapshot(conn, payload, "wall-desk-fixture")
    assert sid
    saved = replay_snapshot(conn, sid)
    assert saved is not None
    echoed = saved["metrics_full"]["wall_desk_snapshot_v1"]
    assert echoed["snapshot_id"] == "fixture-t0"
    assert echoed["raw_gross"] == packet["raw_gross"]
    assert echoed["delta_missing"] == 1
    assert echoed["coverage"]["missing_delta"] == ["CALL-E1-NODELTA"]
    assert echoed["coverage"]["stale"] == ["CALL-E2-STALE"]
    assert echoed["reason_codes"] == ["DELTA_MISSING", "QUOTE_STALE"]
    stored_osi = sorted(c.get("osi") for c in saved["contracts"])
    assert stored_osi == sorted(c.get("osi") for c in first["contracts"])

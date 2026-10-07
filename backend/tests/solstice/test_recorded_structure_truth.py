"""Observed structure survives recording; unknown history is never rebuilt."""
from copy import deepcopy

import duckdb
import pytest

from services.heatmap_history import ensure_tables, record_snapshot, replay_snapshot
from tests.offline_network import deny_external_network  # noqa: F401


def observed_payload():
    return {
        "ticker": "SPY", "asof": "2030-01-02T14:00:00+00:00",
        "source_received_at": "2030-01-02T14:00:01+00:00",
        "event_time": "2030-01-02T13:59:59+00:00",
        "data_source": "observed-structure-fixture", "formula_version": "gex.v2",
        "exposure_basis": "OI", "spot": 100,
        "expiries_used": ["2030-01-04"], "contracts": [],
        "strikes": [{"strike": 100, "gex": 0}],
        "grid": {"grid": {"2030-01-04": {"100": 0}},
                 "vex_grid": {"2030-01-04": {"100": -7}},
                 "vex_meta": {"unit": "USD delta-notional/+1 vol pt", "record_version": "metric-record.v1"}},
        "metrics": {"walls": []},
        "nodes": {"king": {"strike": 100, "gex": 0}, "floors": [],
                  "ceilings": [{"strike": 101.5, "gex": -4}], "gatekeepers": [],
                  "polarity_level": 0, "total_gex": 0, "regime": "neutral"},
        "gamma_flip": {"gamma_flip": 0, "method": "observed-fixture"},
        "flip_zones": [], "net_gex_total": 0, "total_abs_gex": 0,
        "gex_regime": "neutral", "regime": "neutral",
    }


def test_observed_structure_and_signed_cells_survive_in_memory_recording():
    payload = observed_payload()
    untouched = deepcopy(payload)
    with duckdb.connect(":memory:") as conn:
        assert record_snapshot(conn, payload, "observed", "structure-one") == "structure-one"
        rep = replay_snapshot(conn, "structure-one")
        for key in ("nodes", "gamma_flip", "flip_zones", "net_gex_total", "total_abs_gex", "gex_regime", "regime"):
            assert rep["context"]["display"][key] == payload[key]
        assert rep["context"]["display"]["event_time"] == payload["event_time"]
        assert rep["snapshot"]["ticker"] == "SPY"
        assert rep["snapshot"]["snapshot_id"] == "structure-one"
        assert rep["grids"]["grid"]["vex_grid"] == payload["grid"]["vex_grid"]
        assert rep["grids"]["grid"]["vex_meta"] == payload["grid"]["vex_meta"]
    assert payload == untouched


def test_missing_legacy_structure_stays_absent_and_an_existing_snapshot_is_immutable():
    payload = observed_payload()
    keys = ("nodes", "gamma_flip", "flip_zones", "net_gex_total", "total_abs_gex", "gex_regime", "regime")
    legacy = {key: value for key, value in payload.items() if key not in keys}
    with duckdb.connect(":memory:") as conn:
        assert record_snapshot(conn, legacy, "observed", "legacy-one") == "legacy-one"
        before = conn.execute("SELECT context_json FROM heatmap_snapshots_v2 WHERE snapshot_id='legacy-one'").fetchone()[0]
        assert record_snapshot(conn, payload, "observed", "legacy-one") == "legacy-one"
        after = conn.execute("SELECT context_json FROM heatmap_snapshots_v2 WHERE snapshot_id='legacy-one'").fetchone()[0]
        assert before == after
        display = replay_snapshot(conn, "legacy-one")["context"]["display"]
        assert all(key not in display for key in keys)


@pytest.mark.asyncio
async def test_actual_fresh_producer_passes_its_already_computed_structure_to_recording():
    from tests.solstice.test_r14_window_producer import produce

    with duckdb.connect(":memory:") as conn:
        ensure_tables(conn)
        payload = await produce(conn, baseline=False)
        rep = replay_snapshot(conn, payload["snapshotId"])
        assert rep is not None
        display = rep["context"]["display"]
        for key in ("nodes", "gamma_flip", "gex_regime"):
            assert key in payload
            assert display[key] == payload[key]
        # The producer does not export these redundant summaries. Recording
        # must not create them by calculating from another chain or snapshot.
        for key in ("flip_zones", "net_gex_total", "total_abs_gex", "regime"):
            if key not in payload:
                assert key not in display
        assert display["event_time"] == payload["event_time"]
        assert display["map_query"] == payload["map_query"]

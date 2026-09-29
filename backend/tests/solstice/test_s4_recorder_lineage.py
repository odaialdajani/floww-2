"""S4 recorder/history/replay lineage (Spark).

Traces the four activity surfaces from the CANONICAL producer through real
recorder insertion to replay, in an ISOLATED durable DuckDB file that is
closed and reopened, so the check is a genuine durability test rather than a
same-connection read-back.

What this pins:
- the packet is produced by the real producer call path (no hand-injected
  packet fed to the recorder);
- scope identity, values, missingness, freshness and formula version all
  survive a store close/reopen;
- a never-measured metric replays as an explicit unavailable state, never
  as an all-zero history;
- an old record (pre-migration, no metrics column) is preserved and marked
  incomplete instead of being silently regenerated.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

duckdb = pytest.importorskip("duckdb")


SPOT = 300.0
T0 = "2030-01-02T14:00:00+00:00"
T1 = "2030-01-02T14:05:00+00:00"


def _contracts(volume_scale: float = 1.0):
    """Source-shaped contracts: one missing-delta leg, one stale quote."""
    return [
        {"osi": "SPY3000102C00300000", "strike": 300, "expiry": "2030-01-05", "type": "call",
         "gamma": 0.01, "delta": 0.5, "oi": 1000, "volume": 100 * volume_scale,
         "multiplier": 100, "quote_status": "current"},
        {"osi": "SPY3000102P00300000", "strike": 300, "expiry": "2030-01-05", "type": "put",
         "gamma": 0.01, "delta": -0.2, "oi": 1000, "volume": 50 * volume_scale,
         "multiplier": 100, "quote_status": "current"},
        {"osi": "SPY3000102C00300001", "strike": 300, "expiry": "2030-01-05", "type": "call",
         "gamma": 0.01, "delta": None, "oi": 1000, "volume": 10 * volume_scale,
         "multiplier": 100, "quote_status": "stale"},
    ]


def _produce(contracts, *, ticker="SPY", asof=T0, source="public_api", spot=SPOT):
    """The REAL producer path used by the heatmap route (server.py metrics block).

    Deliberately calls the same canonical entry points the route calls, so a
    test can never prove integration by injecting a hand-built packet.
    """
    from domain.exposure_metrics import (
        compute_delta_weighted_oi,
        compute_raw_oi,
        compute_session_delta_volume_gamma,
        compute_volume_gamma,
        wall_metric_breakdown,
    )
    from services.gex_core import (
        compute_gex_grid_delta_weighted,
        compute_gex_grid_session_delta_volume,
        compute_gex_grid_vendor,
        compute_gex_grid_volume_vendor,
    )
    from services.wall_structure import discover_walls

    raw_m = compute_raw_oi(contracts, spot)
    dw_m = compute_delta_weighted_oi(contracts, spot)
    vol_m = compute_volume_gamma(contracts, spot)
    dvol_m = compute_session_delta_volume_gamma(contracts, spot)
    walls = discover_walls(
        [{"strike": 300, "gex": 2700.0, "call_gex": 2700.0, "put_gex": 0.0}], spot,
        scope={"symbol": ticker, "formula": "gex.v2"},
    )
    metrics = {
        "gex_gross_v1": raw_m.gross, "gex_net_v1": raw_m.net,
        "dadgex_gross_v1": dw_m.gross, "dadgex_net_v1": dw_m.net,
        "dadgex_missing_delta": dw_m.missing_delta,
        "volume_gamma_gross": vol_m.gross, "volume_gamma_net": vol_m.net,
        "session_delta_volume_gross_v1": dvol_m.gross,
        "session_delta_volume_net_v1": dvol_m.net,
        "session_delta_volume_missing_delta": dvol_m.missing_delta,
        # Never measured at T0: a window needs a prior comparable observation.
        "window_dadgex_v1": None, "window_dadgex_reason": "HISTORY_NOT_YET_RECORDED",
        "grids": {
            "raw": None,
            "delta": compute_gex_grid_delta_weighted(spot, contracts),
            "activity": compute_gex_grid_volume_vendor(spot, contracts),
            "session_delta_volume": compute_gex_grid_session_delta_volume(spot, contracts),
            "vendor": compute_gex_grid_vendor(spot, contracts),
        },
        "walls": walls,
        "wall_metrics": wall_metric_breakdown(walls, contracts, spot),
        "formula_version": "gex.v2",
    }
    return {
        "ticker": ticker, "spot": spot, "asof": asof, "source_received_at": asof,
        "data_source": source, "exposure_basis": "OI", "formula_version": "gex.v2",
        "expiries_used": ["2030-01-05"], "strikes": [], "grid": {},
        "contracts": contracts, "metrics": metrics,
        "coverage": {"requested": len(contracts), "returned": len(contracts),
                     "usable": raw_m.usable, "truncated": False},
    }


@pytest.fixture
def store(tmp_path):
    """An isolated durable store, closed and reopened between the two legs."""
    path = tmp_path / "solstice_lineage.duckdb"
    yield path
    for suffix in ("", ".wal"):
        p = Path(str(path) + suffix)
        if p.exists():
            p.unlink()


def test_activity_surfaces_survive_a_durable_reopen(store):
    from services.heatmap_history import ensure_tables, record_snapshot, replay_snapshot

    payload = _produce(_contracts())
    conn = duckdb.connect(str(store))
    try:
        ensure_tables(conn)
        sid = record_snapshot(conn, payload, "SPY:day:0:60")
        assert sid
    finally:
        conn.close()

    # Reopened from disk: a genuine durability read, not a same-handle cache.
    conn = duckdb.connect(str(store))
    try:
        replayed = replay_snapshot(conn, sid)
    finally:
        conn.close()

    snap = replayed["snapshot"]
    m = replayed["metrics_full"]
    assert snap["ticker"] == "SPY"
    assert snap["formula_version"] == "gex.v2"
    assert snap["data_source"] == "public_api"
    assert snap["asof_ts"] == T0
    # Scope identity + provenance of the window side is declared, not implied.
    # u = 0.01*100*300^2*0.01 = 900 per contract unit.
    # session delta-volume gross = 900*.5*100 + 900*.2*50 = 54,000
    # net = call leg - put leg = 45,000 - 9,000 = 36,000
    assert m["session_delta_volume_gross_v1"] == pytest.approx(54_000.0)
    assert m["session_delta_volume_net_v1"] == pytest.approx(36_000.0)
    assert m["session_delta_volume_missing_delta"] == 1
    assert m["dadgex_missing_delta"] == 1
    # Σ c·u·V has NO delta requirement, so the delta-missing leg still
    # contributes (900*10 = 9,000). The two activity surfaces therefore
    # measure different populations over the same contracts — that is the
    # whole reason they must stay distinct metrics.
    assert m["volume_gamma_gross"] == pytest.approx(900.0 * (100 + 50 + 10))
    assert m["session_delta_volume_gross_v1"] == pytest.approx(900.0 * (100 * 0.5 + 50 * 0.2))
    assert m["grids"]["session_delta_volume"]["exposure_basis"] == "VOLUME_DELTA_WEIGHTED"
    assert m["grids"]["activity"]["exposure_basis"] == "VOLUME"
    assert m["grids"]["session_delta_volume"]["missing_delta"] == 1
    # A metric that has never been measured replays as an explicit
    # unavailable state, not as an all-zero history and not as a
    # regenerated current-Greek value.
    assert m["window_dadgex_v1"] is None
    assert m["window_dadgex_reason"] == "HISTORY_NOT_YET_RECORDED"
    # Every contract observation round-trips with its identity fields.
    osis = sorted(c["osi"] for c in replayed["contracts"])
    assert osis == ["SPY3000102C00300000", "SPY3000102C00300001", "SPY3000102P00300000"]
    assert all(c["type"] in ("call", "put") for c in replayed["contracts"])
    assert {c["strike"] for c in replayed["contracts"]} == {300.0}


def test_never_measured_metric_replays_unavailable_even_when_greeks_exist(store):
    """The recorded contracts carry a full Greek set, and the window is still
    None. A recorded contract row must not be re-read as 'a window we could
    compute' — that is the regenerated-Greek masquerade."""
    from services.heatmap_history import ensure_tables, record_snapshot, replay_snapshot

    conn = duckdb.connect(str(store))
    try:
        ensure_tables(conn)
        sid = record_snapshot(conn, _produce(_contracts()), "SPY:day:0:60")
    finally:
        conn.close()
    conn = duckdb.connect(str(store))
    try:
        replayed = replay_snapshot(conn, sid)
    finally:
        conn.close()
    m = replayed["metrics_full"]
    assert replayed["contracts"], "contract observations were recorded"
    assert all(c.get("gamma") for c in replayed["contracts"]), "Greeks are present on disk"
    assert m["window_dadgex_v1"] is None
    assert m["window_dadgex_reason"] == "HISTORY_NOT_YET_RECORDED"


def test_pre_migration_record_is_preserved_and_marked_incomplete(store):
    from services.heatmap_history import ensure_tables, record_snapshot, replay_snapshot

    conn = duckdb.connect(str(store))
    try:
        ensure_tables(conn)
        # A legacy-shaped row: no metrics column value at all.
        conn.execute(
            "INSERT INTO heatmap_snapshots_v2 (snapshot_id, ticker, query_key, spot, "
            "data_source, exposure_basis, formula_version, asof_ts, n_contracts) "
            "VALUES ('legacy-1', 'SPY', 'SPY:day:0:60', 300.0, 'public_api', 'OI', "
            "'gex.v1', '2029-01-02T14:00:00+00:00', 0)"
        )
        # A fresh, correctly-produced record alongside it.
        sid = record_snapshot(conn, _produce(_contracts()), "SPY:day:0:60")
    finally:
        conn.close()

    conn = duckdb.connect(str(store))
    try:
        legacy = replay_snapshot(conn, "legacy-1")
        fresh = replay_snapshot(conn, sid)
        n = conn.execute("SELECT COUNT(*) FROM heatmap_snapshots_v2").fetchone()[0]
    finally:
        conn.close()

    assert n == 2, "the old record must be preserved, not overwritten"
    assert legacy["metrics_full"] is None, "absent metrics stay absent, never regenerated"
    assert legacy["snapshot"]["formula_version"] == "gex.v1"
    assert fresh["metrics_full"]["session_delta_volume_missing_delta"] == 1

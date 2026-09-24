"""R5-B red tests: complete recording, restart, replay, compare (G2/R05-R07)."""

import sys

sys.path.insert(0, "backend")


def _payload(**kw):
    p = {"ticker": "SPY", "expiries_used": ["2030-01-15"], "spot": 500.0,
         "mode": "day", "dte": None, "scalp": False,
         "data_source": "public_api", "exposure_basis": "OI",
         "formula_version": "gex.v2",
         "asof": "2030-01-02T14:00:00+00:00",
         "source_received_at": "2030-01-02T14:00:01+00:00",
         "contracts": [{"osi": "C1", "expiry": "2030-01-15", "strike": 500,
                        "type": "call", "multiplier": 100.0, "bid": 1.0, "ask": 1.2,
                        "volume": 100, "oi": 50, "iv": 0.2, "delta": 0.5, "gamma": 0.05}],
         "strikes": [{"strike": 500, "gex": 1e6}],
         "grid": {"grid": {"2030-01-15": {"500": 1e6}}},
         "metrics": {"walls": [{"wall_id": "w_1", "low": 498, "high": 502}]},
         "quality": {"state": "usable", "reasonCodes": [], "setupEligible": True,
                     "executionEligible": False, "tradeSideCapability": "none"}}
    p.update(kw)
    return p


def test_r05_recorded_cells_reproduce_grid():
    import duckdb

    from services.heatmap_history import record_snapshot, replay_snapshot
    conn = duckdb.connect(":memory:")
    sid = record_snapshot(conn, _payload(), "q")
    rep = replay_snapshot(conn, sid)
    cells = (rep.get("grids") or {}).get("grid", {}).get("2030-01-15", {})
    assert cells.get("500") == 1e6, rep.get("grids")


def test_r06_stored_contracts_match_window_identity():
    import duckdb

    from services.heatmap_history import normalize_stored_contract, record_snapshot, replay_snapshot
    conn = duckdb.connect(":memory:")
    sid = record_snapshot(conn, _payload(), "q")
    rep = replay_snapshot(conn, sid)
    c = normalize_stored_contract(rep["contracts"][0])
    assert c["type"] == "call" and c["strike"] == 500.0 and c["osi"] == "C1"
    assert c["delta"] == 0.5 and c["gamma"] == 0.05
    # Same-contract matching works record -> replay.
    from services.solstice_enrichment import window_contract_activity
    cur = [dict(c, volume=140)]
    out = window_contract_activity([c], cur, 500.0)
    assert out["status"] == "ok" and len(out["contracts"]) == 1


def test_r07_commit_failure_not_acknowledged():
    import duckdb

    from services import heatmap_history as hh
    inner = duckdb.connect(":memory:")
    hh.ensure_tables(inner)

    class BoomConn:
        def __init__(self, wrapped):
            self._wrapped = wrapped

        def execute(self, sql, *a, **k):
            if isinstance(sql, str) and sql.strip().upper() == "COMMIT":
                raise RuntimeError("injected COMMIT failure")
            return self._wrapped.execute(sql, *a, **k)

        def __getattr__(self, name):
            return getattr(self._wrapped, name)

    conn = BoomConn(inner)
    sid = hh.record_snapshot(conn, _payload(), "q")
    assert sid is None
    n = inner.execute("SELECT COUNT(*) FROM heatmap_snapshots_v2").fetchone()[0]
    assert n == 0

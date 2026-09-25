"""R7-03 red tests: complete display projection persists; replay restores it."""

import sys

sys.path.insert(0, "backend")


def _payload(**kw):
    p = {"ticker": "SPY", "expiries_used": ["2030-01-15"], "spot": 500.0,
         "mode": "day", "dte": None, "scalp": False,
         "data_source": "public_api", "exposure_basis": "OI",
         "formula_version": "gex.v2",
         "asof": "2030-01-02T14:00:00+00:00",
         "source_received_at": "2030-01-02T14:00:01+00:00",
         "contracts": [],
         "strikes": [{"strike": 500, "gex": 1e6}],
         "grid": {"expiries": ["2030-01-15"], "strikes": [500],
                  "grid": {"2030-01-15": {"500": 1e6}}},
         "metrics": {"walls": [{"wall_id": "w_1", "low": 498, "high": 502}],
                     "wall_window": {"w_1": {"window_daddex": 42.0}},
                     "nearest_walls": [{"wall_id": "w_1", "low": 498, "high": 502}],
                     "grids": {"grid": {"expiries": ["2030-01-15"], "strikes": [500],
                                        "grid": {"2030-01-15": {"500": 1e6}}}}},
         "quality": {"state": "usable", "reasonCodes": [], "setupEligible": False,
                     "executionEligible": False, "tradeSideCapability": "none"},
         "scenarios": [{"wall_id": "w_1", "name": "Bounce watch"}],
         "interactions": [{"wall_id": "w_1", "state": "testing"}],
         "session": {"entry_allowed": False, "reasons": ["MARKET_CLOSED"]},
         "playbook": {"side": "none"},
         "scout": {"calls": 0, "puts": 0, "rejected": {}},
         "gamma_regime_v1": {"sign": "positive"},
         "patterns_v1": [],
         "vanna_v1": {"by_expiry": {}},
         "moneyness": {"buckets": []}}
    p.update(kw)
    return p


def test_r07b_context_and_wall_metrics_survive_restart(tmp_path):
    import duckdb

    from services.heatmap_history import record_snapshot, replay_snapshot
    dbfile = str(tmp_path / "solstice.duckdb")
    conn = duckdb.connect(dbfile)
    sid = record_snapshot(conn, _payload(), "q")
    conn.close()
    conn2 = duckdb.connect(dbfile)
    rep = replay_snapshot(conn2, sid)
    assert rep["metrics_full"]["wall_window"] == {"w_1": {"window_daddex": 42.0}}
    assert rep["metrics_full"]["nearest_walls"][0]["wall_id"] == "w_1"
    ctx = rep["context"]
    assert ctx["session"] == {"entry_allowed": False, "reasons": ["MARKET_CLOSED"]}
    assert ctx["scout"] == {"calls": 0, "puts": 0, "rejected": {}}
    assert ctx["gamma_regime_v1"] == {"sign": "positive"}
    conn2.close()


def test_r07c_legacy_record_without_new_columns_replays_gracefully(tmp_path):
    import duckdb

    from services.heatmap_history import record_snapshot, replay_snapshot
    dbfile = str(tmp_path / "solstice.duckdb")
    conn = duckdb.connect(dbfile)
    sid = record_snapshot(conn, _payload(), "q")
    # Simulate a pre-migration record: drop the R7-03 columns.
    conn.execute("ALTER TABLE heatmap_snapshots_v2 DROP COLUMN metrics_full_json")
    conn.execute("ALTER TABLE heatmap_snapshots_v2 DROP COLUMN context_json")
    conn.close()
    conn2 = duckdb.connect(dbfile)
    rep = replay_snapshot(conn2, sid)
    assert rep["metrics_full"] is None and rep["context"] is None
    # Cells still restore; the adapter (not storage) marks partial.
    assert rep["grids"]["grid"]["grid"]["2030-01-15"]["500"] == 1e6
    conn2.close()

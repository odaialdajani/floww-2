"""Node velocity: per-strike d(GEX)/dt between adjacent snapshots (P2).

RED first: module does not exist. Pure function over recorded rows only —
no provider reads, no spend. Added/removed strikes are not comparable
observations: their rate stays unknown (None), never zero-filled.
"""
import pytest

from services.chart_velocity import node_velocity


def test_retained_strike_velocity_and_growth():
    before = [{"strike": 500, "gex": 1e6}]
    after = [{"strike": 500, "gex": 2e6}]
    out = node_velocity(before, after, 3600.0)
    assert len(out) == 1
    row = out[0]
    assert row["strike"] == 500
    assert row["before"] == 1e6 and row["after"] == 2e6
    assert row["delta"] == pytest.approx(1e6)
    assert row["velocity"] == pytest.approx(1e6 / 3600.0)
    assert row["growth"] == pytest.approx(1.0)
    assert row["status"] == "retained"


def test_zero_before_growth_undefined_velocity_known():
    before = [{"strike": 500, "gex": 0.0}]
    after = [{"strike": 500, "gex": 5e5}]
    (row,) = node_velocity(before, after, 1800.0)
    assert row["growth"] is None  # magnitude % undefined after zero
    assert row["velocity"] == pytest.approx(5e5 / 1800.0)
    assert row["status"] == "retained"


def test_added_and_removed_strikes_stay_unknown():
    before = [{"strike": 500, "gex": 1e6}]
    after = [{"strike": 510, "gex": 2e6}]
    out = node_velocity(before, after, 3600.0)
    by_strike = {r["strike"]: r for r in out}
    assert by_strike[510]["status"] == "added"
    assert by_strike[510]["velocity"] is None
    assert by_strike[510]["growth"] is None
    assert by_strike[500]["status"] == "removed"
    assert by_strike[500]["velocity"] is None
    assert by_strike[500]["growth"] is None


def test_non_positive_dt_gives_unknown_rates():
    before = [{"strike": 500, "gex": 1e6}]
    after = [{"strike": 500, "gex": 2e6}]
    for bad_dt in (0.0, -60.0, float("nan")):
        (row,) = node_velocity(before, after, bad_dt)
        assert row["delta"] == pytest.approx(1e6)
        assert row["velocity"] is None
        # Growth is timeless (needs no clock) — only the rate is unknown.
        assert row["growth"] == pytest.approx(1.0)


def test_non_finite_and_missing_gex_are_not_comparable_before():
    before = [{"strike": 500, "gex": 1e6}, {"strike": 501, "gex": float("nan")},
              {"strike": 502}, {"strike": 503, "gex": True},
              {"strike": 504, "gex": 3e5}, "junk-row", None]
    after = [{"strike": 500, "gex": 2e6}, {"strike": 501, "gex": 2e6},
             {"strike": 502, "gex": 2e6}, {"strike": 503, "gex": 2e6},
             {"strike": 505, "gex": 1e5}, "junk-row", None]
    out = node_velocity(before, after, 3600.0)
    by_strike = {r["strike"]: r for r in out}
    assert by_strike[500]["status"] == "retained"
    # Unparseable-before strikes are additions, not comparable observations.
    for added in (501, 502, 503, 505):
        assert by_strike[added]["status"] == "added"
        assert by_strike[added]["velocity"] is None
    assert by_strike[504]["status"] == "removed"
    assert by_strike[504]["velocity"] is None


def test_output_sorted_by_strike():
    before = [{"strike": 510, "gex": 1e6}, {"strike": 500, "gex": 1e6}]
    after = [{"strike": 500, "gex": 2e6}, {"strike": 510, "gex": 2e6}]
    out = node_velocity(before, after, 60.0)
    assert [r["strike"] for r in out] == [500, 510]


def test_compare_snapshots_carries_velocities():
    import duckdb

    from services.heatmap_history import compare_snapshots, record_snapshot
    conn = duckdb.connect(":memory:")

    def payload(asof, gex):
        return {"ticker": "TST", "expiries_used": ["2030-01-15"], "spot": 500.0,
                "data_source": "public_api", "exposure_basis": "OI",
                "formula_version": "gex.v2", "asof": asof,
                "source_received_at": asof,
                "contracts": [{"strike": 500, "kind": "call", "iv": 0.05, "oi": 1000}],
                "strikes": [{"strike": 500, "gex": gex, "total_volume": 1000}],
                "metrics": {"walls": [{"wall_id": "w_a", "low": 498, "high": 502,
                                       "mid": 500, "gross": gex, "members": [500]}]}}
    assert record_snapshot(conn, payload("2030-01-02T00:00:00+00:00", 1e6), "q")
    assert record_snapshot(conn, payload("2030-01-02T01:00:00+00:00", 2e6), "q")
    cmp_ = compare_snapshots(conn, "TST", "2030-01-02")
    assert cmp_["status"] == "ok"
    assert cmp_["velocity_dt_seconds"] == 3600.0
    assert cmp_["velocities"][0]["strike"] == 500
    assert cmp_["velocities"][0]["velocity"] == pytest.approx(1e6 / 3600.0)
    assert cmp_["velocities"][0]["growth"] == pytest.approx(1.0)
    # Existing keys untouched by the additive wiring.
    assert cmp_["strike_deltas"][0]["delta"] == 1e6
    conn.close()

"""Independent counterexamples found during the November 7 integration review."""

import pytest

from services.heatseeker import calc_air_pockets, calc_velocity_mode, group_replay_sessions


def _chain():
    return [
        {"strike": strike, "gamma": 0.05, "open_interest": 1000, "type": "C"}
        for strike in range(95, 106)
    ]


@pytest.mark.parametrize("field", ["gamma", "open_interest"])
@pytest.mark.parametrize("value", [None, "bad", float("nan"), float("inf"), -1, True])
def test_unknown_exposure_is_never_a_measured_zero_air_pocket(field, value):
    contracts = _chain()
    for contract in contracts:
        if contract["strike"] in (99, 100):
            contract[field] = value
    result = calc_air_pockets(100, contracts)
    assert result["air_pockets"] == []
    assert result["coverage_status"] == "unknown"
    assert result["strikes_unknown_exposure"] == 2


def test_partial_strike_exposure_cannot_certify_a_thin_run():
    contracts = _chain()
    for contract in contracts:
        if contract["strike"] in (99, 100):
            contract["gamma"] = 0
    contracts.append({"strike": 99, "type": "P", "gamma": None, "open_interest": 1000})
    result = calc_air_pockets(100, contracts)
    assert result["air_pockets"] == []
    assert result["coverage_status"] == "unknown"


def test_measured_zero_exposure_still_forms_a_contiguous_pocket():
    contracts = _chain()
    for contract in contracts:
        if contract["strike"] in (99, 100):
            contract["gamma"] = 0
    result = calc_air_pockets(100, contracts)
    assert result["coverage_status"] == "ok"
    assert [(p["low"], p["high"]) for p in result["air_pockets"]] == [(99, 100)]


def _node_history(last_strike):
    return [
        {"timestamp": "2026-11-06T14:30:00Z", "king_node_strike": 100, "king_node_gex": 1e9},
        {"timestamp": "2026-11-06T14:35:00Z", "king_node_strike": last_strike, "king_node_gex": 2e9},
    ]


def test_changing_king_node_does_not_measure_same_node_exposure_growth():
    result = calc_velocity_mode(_node_history(105))
    assert result["velocity_strikes_per_min"] == 1
    assert result["exposure_change"]["measured"] is False
    assert result["exposure_change"]["reason"] == "NODE_CHANGED"


def test_identified_same_node_retains_measured_exposure_change():
    result = calc_velocity_mode(_node_history(100))
    assert result["velocity_strikes_per_min"] == 0
    assert result["exposure_change"] == {
        "measured": True, "unit": "dollars_per_min", "value": 200000000,
    }


@pytest.mark.parametrize("asof", ["not-a-time", "2026-11-06T14:30:00", "2026-11-06", ""])
def test_unusable_replay_time_cannot_certify_a_session(asof):
    result = group_replay_sessions(
        [{"asof": asof, "query_key": "same-scope", "snapshot_id": "bad"}],
        expected_cadence_s=300, day="2026-11-06", ticker="SPY",
    )
    assert result["status"] != "ok"
    assert result["gap_coverage"] == "unknown"
    assert result["n_snapshots"] == 0
    assert result["rows_without_timestamp"] == 1


def test_invalid_row_keeps_partial_replay_coverage_explicit():
    result = group_replay_sessions(
        [
            {"asof": "2026-11-06T14:30:00Z", "query_key": "same-scope", "snapshot_id": "valid"},
            {"asof": "not-a-time", "query_key": "same-scope", "snapshot_id": "invalid"},
        ], expected_cadence_s=300,
    )
    assert result["status"] == "partial"
    assert result["gap_coverage"] == "unknown"
    assert result["n_snapshots"] == 1
    assert result["rows_without_timestamp"] == 1


def test_replay_gap_order_uses_instants_across_explicit_offsets():
    result = group_replay_sessions(
        [
            {"asof": "2026-11-06T14:30:00Z", "query_key": "same-scope", "snapshot_id": "later"},
            {"asof": "2026-11-06T15:00:00+01:00", "query_key": "same-scope", "snapshot_id": "earlier"},
        ], expected_cadence_s=300,
    )
    session = result["sessions"][0]
    assert [row["snapshot_id"] for row in session["snapshots"]] == ["earlier", "later"]
    assert session["gaps"][0]["gap_s"] == 1800

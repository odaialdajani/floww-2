"""Historical price lines keep stored conventions, scope, clocks and missing values."""
import json
from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from services.agent.display_map import map_cache_key
from services.price_node_history import scope_id
from services.recorded_price_levels import MAX_DETAIL_RECORDS, _metric_cells, enrich_recorded_levels


@pytest.fixture
def stored():
    query = {"expiries": 1, "mode": "day", "dte": None, "scalp": False, "withTaps": True, "maxStrikes": 80}
    main = {"strikes": [95, 100, 105], "expiries": ["2026-10-09"], "grid": {"2026-10-09": {"95": 1, "100": 2, "105": 3}}}
    for metric in ("vex", "charm"):
        main[metric + "_grid"] = {"2026-10-09": {"95": -200, "100": 12, "105": 300 if metric == "charm" else 0}}
        main[metric + "_meta"] = {"record_version": "metric-record.v1", "metric_id": "vex_net_1volpt" if metric == "vex" else "charm_net_1pct_year_v1",
                                 "unit": "USD delta-notional/+1 vol pt" if metric == "vex" else "dollar_charm_1pct_per_year",
                                 "formula_version": "gex.v2", "model": "local-bs-vanna.v1" if metric == "vex" else "local-bs-charm.v1",
                                 "exposure_basis": "VEX_1VOLPT" if metric == "vex" else "CHARM", "weight_basis": "OI", "status": "ok",
                                 "quarantined": 0, "invalid_type": 0, "missing_vanna_inputs" if metric == "vex" else "missing_charm_inputs": 0,
                                 "data_source": "saved-provider", "map_query": query, "scope": {"strikes": main["strikes"], "expiries": main["expiries"]},
                                 "event_time": "2026-10-06T14:00:00Z", "fetched_at": "2026-10-06T14:00:05Z", "available_at": "2026-10-06T14:00:10Z"}
    return {"snapshot_id": "saved-1", "ticker": "SPY", "query_key": map_cache_key("SPY", query), "expiries": ["2026-10-09"],
            "formula_version": "gex.v2", "exposure_basis": "OI", "asof_ts": "2026-10-06T14:00:10Z", "received_at": "2026-10-06T14:00:12Z",
            "data_source": "saved-provider", "grids_json": {"version": "grids.v1", "grid": main},
            "context_json": {"display": {"map_query": query, "event_time": "2026-10-06T14:00:00Z", "fetched_at": "2026-10-06T14:00:05Z", "stale": False}}}


def extract(row, time="2026-10-06T14:05:00Z"):
    return _metric_cells(row, "SPY", scope_id(row), datetime.fromisoformat(time.replace("Z", "+00:00")).timestamp())


def test_each_line_comes_from_its_own_largest_recorded_cell_not_gamma_structure(stored):
    before = deepcopy(stored)
    levels, status = extract(stored)
    assert levels["vex"][0]["level"] == 95 and levels["vex"][0]["value"] == -200
    assert levels["charm"][0]["level"] == 105 and levels["charm"][0]["value"] == 300
    assert levels["vex"][0]["age_seconds"] == 300
    assert status == {"vex": "available", "charm": "available"}
    assert stored == before


@pytest.mark.parametrize(("field", "value"), [("unit", "other"), ("model", "today-rebuilt"), ("record_version", None), ("data_source", "another"), ("weight_basis", "VOLUME"), ("quarantined", 1), ("missing_vanna_inputs", 1), ("status", "partial")])
def test_unqualified_vex_cannot_borrow_a_charm_or_gamma_level(stored, field, value):
    stored["grids_json"]["grid"]["vex_meta"][field] = value
    levels, statuses = extract(stored)
    assert "vex" not in levels and "vex" not in statuses
    assert levels["charm"][0]["level"] == 105


@pytest.mark.parametrize("cell", [None, True, "12", float("inf")])
def test_missing_or_invalid_cells_do_not_create_a_complete_strongest_level(stored, cell):
    stored["grids_json"]["grid"]["vex_grid"]["2026-10-09"]["100"] = cell
    levels, status = extract(stored)
    assert "vex" not in levels and "vex" not in status


def test_future_receipt_and_old_source_events_cannot_become_fresh_historical_lines(stored):
    assert extract(stored, "2026-10-06T14:00:11Z") == ({}, {})
    assert extract(stored, "2026-10-06T14:16:00Z") == ({}, {})
    stored["context_json"]["display"]["event_time"] = "2026-10-06T13:40:00Z"
    for metric in ("vex", "charm"):
        stored["grids_json"]["grid"][metric + "_meta"]["event_time"] = "2026-10-06T13:40:00Z"
    assert extract(stored) == ({}, {})


def test_scope_stock_and_legacy_version_conflicts_remain_gaps(stored):
    for change in ({"ticker": "QQQ"}, {"query_key": "another-view"}, {"expiries": ["2026-10-16"]}, {"grids_json": {"version": "unknown"}}):
        assert extract({**stored, **change}) == ({}, {})


def test_measured_zero_is_reported_without_inventing_a_price_concentration(stored):
    for metric in ("vex", "charm"):
        stored["grids_json"]["grid"][metric + "_grid"]["2026-10-09"] = {"95": 0, "100": 0, "105": 0}
    assert extract(stored) == ({}, {"vex": "zero", "charm": "zero"})


def test_tied_strikes_keep_their_own_cell_and_expiry_identity(stored):
    stored["grids_json"]["grid"]["vex_grid"]["2026-10-09"]["105"] = 200
    levels, _ = extract(stored)
    assert [node["level"] for node in levels["vex"]] == [95, 105]
    assert all(node["tied"] for node in levels["vex"])


def test_reader_is_bounded_to_selected_snapshots_and_keeps_inputs_unchanged(stored):
    frame = {"time": "2026-10-06T14:05:00Z", "snapshot_id": "saved-1", "nodes": [], "open": 100, "high": 102, "low": 99, "close": 101}
    history = {"ticker": "SPY", "query_key": scope_id(stored), "frames": [frame], "candles_with_recorded_nodes": 0}
    before = deepcopy(history)
    calls = []

    def query(sql, args):
        calls.append((sql, args))
        return [{"name": field} for field in ("grids_json", "context_json", "data_source")] if sql.startswith("PRAGMA") else [stored]

    result = enrich_recorded_levels(history, SimpleNamespace(query_strict=query))
    assert len(result["frames"][0]["nodes"]) == 2
    assert result["candles_with_recorded_nodes"] == 1 and history == before
    assert calls[1][1][-1] == "saved-1" and "LIMIT 256" in calls[1][0]
    assert result["metric_line_coverage"]["vex"]["checked_candles"] == 1


def test_unavailable_storage_and_missing_legacy_fields_never_claim_zero_lines(stored):
    history = {"ticker": "SPY", "query_key": scope_id(stored), "frames": [{"time": "2026-10-06T14:05:00Z", "snapshot_id": "saved-1", "nodes": []}]}

    def broken(sql, args):
        raise RuntimeError("unavailable")

    result = enrich_recorded_levels(history, SimpleNamespace(query_strict=broken))
    assert result["metric_details_status"] == "unavailable"
    assert result["frames"][0]["nodes"] == []
    assert "metric_status" not in result["frames"][0]
    assert enrich_recorded_levels(history, SimpleNamespace(query_strict=lambda *_: []))["frames"][0]["nodes"] == []


def test_oldest_details_beyond_the_bound_stay_unknown(stored):
    history = {"ticker": "SPY", "query_key": scope_id(stored), "frames": [{"time": "2026-10-06T14:05:00Z", "snapshot_id": f"saved-{index}", "nodes": []} for index in range(MAX_DETAIL_RECORDS + 1)]}
    calls = []

    def query(sql, args):
        calls.append((sql, args))
        return [{"name": field} for field in ("grids_json", "context_json", "data_source")] if sql.startswith("PRAGMA") else []

    result = enrich_recorded_levels(history, SimpleNamespace(query_strict=query))
    assert result["metric_details_truncated"] is True and len(calls[1][1]) == MAX_DETAIL_RECORDS + 3
    assert "saved-0" not in calls[1][1]


def test_bad_or_oversized_json_does_not_enter_the_saved_line_projection(stored):
    for value in ("{bad", json.dumps({"version": "grids.v1", "padding": "x" * 131073}), '{"version":"grids.v1","grid":NaN}'):
        assert extract({**stored, "grids_json": value}) == ({}, {})

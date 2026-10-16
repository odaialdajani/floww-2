"""Scope identity and candle-time gap reasons, without mixing saved views."""
import pytest

from services.price_node_history import build_history, scope_id
from services.solstice_scope import attach_scope_echo
from tests.offline_network import deny_external_network  # noqa: F401

BAR = {"t":"2026-10-06T14:00:00Z","o":100,"h":102,"l":99,"c":101}


def row(scope="saved",asof="2026-10-06T13:59:00Z",walls=None):
    return {"snapshot_id":"snapshot-1","ticker":"SPY","query_key":scope,"expiries":["2026-10-09"],"formula_version":"gex.v2","exposure_basis":"OI","asof_ts":asof,"received_at":asof,"walls_json":[{"wall_id":"wall-1","mid":100}] if walls is None else walls}


def test_heatmap_emits_the_recorder_scope_not_the_request_cache_key():
    payload={"ticker":"SPY","expiries_used":["2026-10-09"],"exposure_basis":"OI"}
    request="SPY:4:day:None:False:True:80"
    saved="SPY:day:None:False"
    actual=attach_scope_echo(payload,request,history_query_key=saved,formula_version="gex.v2")
    assert actual["scope_echo"]==request
    assert actual["history_scope"]==scope_id(row(saved))
    assert actual["history_scope"]!=request


@pytest.mark.parametrize("expiries",[None,[],"2026-10-09"])
def test_missing_expiry_identity_does_not_invent_history_selector(expiries):
    payload={"ticker":"SPY","expiries_used":expiries,"exposure_basis":"OI"}
    out=attach_scope_echo(payload,"K",history_query_key="saved",formula_version="gex.v2")
    assert "history_scope" not in out


def test_coverage_distinguishes_a_different_saved_scope_without_borrowing_its_nodes():
    saved=row()
    result=build_history("SPY",[BAR],[saved],"foreign")
    assert result["candles_with_recorded_nodes"]==0
    assert result["node_coverage"]["scope_status"]=="scope_not_available"
    assert result["node_coverage"]["gap_counts"]=={"no_prior_observation":1,"observation_too_old":0,"recorded_without_nodes":0}
    assert result["frames"][0]["nodes"]==[]


@pytest.mark.parametrize(("saved","reason"),[(row(asof="2026-10-06T14:01:00Z"),"no_prior_observation"),(row(asof="2026-10-06T13:00:00Z"),"observation_too_old"),(row(walls=[]),"recorded_without_nodes")])
def test_candle_gap_reasons_preserve_time_and_empty_record_distinctions(saved,reason):
    result=build_history("SPY",[BAR],[saved],scope_id(saved))
    assert result["node_coverage"]["gap_counts"][reason]==1
    assert sum(result["node_coverage"]["gap_counts"].values())==1
    assert result["candles_with_recorded_nodes"]==0


def test_matching_coverage_does_not_count_an_empty_record_as_missing_observation():
    saved=row()
    result=build_history("SPY",[BAR],[saved],scope_id(saved))
    assert result["node_coverage"]["scope_status"]=="available"
    assert sum(result["node_coverage"]["gap_counts"].values())==0
    assert result["candles_with_recorded_nodes"]==1


@pytest.mark.asyncio
async def test_actual_producer_echo_resolves_to_its_immutable_record(deny_external_network):
    import duckdb

    from tests.solstice.test_r14_window_producer import produce

    with duckdb.connect(":memory:") as conn:
        payload = await produce(conn)
        cursor = conn.execute("SELECT query_key,expiries,formula_version,exposure_basis FROM heatmap_snapshots_v2 WHERE snapshot_id=?", [payload["snapshotId"]])
        stored = dict(zip([col[0] for col in cursor.description], cursor.fetchone(), strict=True))
        assert payload["history_scope"] == scope_id(stored)
        assert payload["history_scope"] != payload["scope_echo"]

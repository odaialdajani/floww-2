"""Current-data reconciliation must not turn option activity into trade direction."""
from datetime import UTC, datetime

from services.node_confluence import flow_at_strike, node_brief


def test_call_heavy_volume_is_context_not_bullish_evidence():
    row = node_brief("SPY", [{"strike": 500, "gex": -123, "call_volume": 1000, "put_volume": 0}])["rows"][0]
    assert row["confluence"]["dimensions"]["microstructure"]["inputs_status"] == "context_only"
    assert row["confluence"]["total"] is None


def test_option_premium_does_not_select_the_underlying_level():
    result = flow_at_strike([{"strike": 500, "price": 2, "type": "put"}, {"premium": 500}], 500)
    assert result["count"] == 1
    assert result["unpriced_rows"] == 1
    assert result["put_side"] == 1


def test_bought_put_uses_declared_alert_bias_not_buy_as_bullish():
    alert = {"strike": 500, "side": "BUY", "type": "put", "bias": "BEARISH", "conviction": 80,
             "asof_ts": datetime.now(UTC).isoformat()}
    result = flow_at_strike([alert], 500)
    assert result["direction_net"] == -1
    assert result["call_side"] == 0 and result["put_side"] == 1


def test_cumulative_snapshot_has_no_direction_even_with_old_bias():
    alert = {"strike": 500, "side": "FLOW", "bias": "BULLISH", "conviction": 99,
             "asof_ts": datetime.now(UTC).isoformat(), "context": '{"activity_basis":"cumulative_snapshot"}'}
    result = flow_at_strike([alert], 500)
    assert result["direction_net"] is None
    assert result["direction_status"] == "unavailable"


def test_old_alert_bias_cannot_tilt_current_node_score():
    row = node_brief("SPY", [{"strike": 500, "gex": 123}], flow_rows=[{
        "strike": 500, "side": "BUY", "bias": "BULLISH", "conviction": 99, "asof_ts": "2020-01-01T00:00:00Z"
    }])["rows"][0]
    assert row["confluence"]["total"] is None


def test_persisted_snapshot_context_stays_nondirectional():
    result = flow_at_strike([{"strike": 500, "side": "BUY", "bias": "BULLISH", "conviction": 99,
        "asof_ts": datetime.now(UTC).isoformat(), "context_json": '{"activity_basis":"cumulative_snapshot"}'}], 500)
    assert result["direction_net"] is None

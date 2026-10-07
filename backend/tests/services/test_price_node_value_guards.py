"""Unknown numeric and historical-window states cannot become invented prices."""
import pytest

from services.price_node_history import build_history, recorded_nodes


@pytest.mark.parametrize("bad", [True, False, None, "", float("nan"), float("inf")])
def test_unknown_or_boolean_price_does_not_become_a_real_candle(bad):
    result = build_history("SPY", [{"t": "2026-10-06T14:00:00Z", "o": bad, "h": 10, "l": 0.5, "c": 1}], [])
    assert result["frames"] == []


def test_boolean_node_does_not_become_a_one_dollar_historical_level():
    assert recorded_nodes({"walls_json": [{"wall_id": "unknown", "mid": True}]}) == []

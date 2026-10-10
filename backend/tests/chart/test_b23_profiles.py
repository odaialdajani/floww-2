"""B23 profiles. Synthetic only."""
def test_poc_ties_down_and_va():
    from services.chart_profiles import poc, value_area
    rows = [{"price": 100, "volume": 10}, {"price": 101, "volume": 10}, {"price": 102, "volume": 5}]
    assert poc(rows)["price"] == 100
    va = value_area(rows, pct=0.70)
    assert va["status"] == "ok"
    assert va["low"] <= 100 <= va["high"]
    assert value_area([], 0.7)["status"] == "unavailable"


def test_naked_levels_end_at_revisit():
    from services.chart_profiles import naked_levels
    levels = [{"price": 100.0, "session_start": "2026-10-06"}, {"price": 200.0, "session_start": "2026-10-06"}]
    bars = [{"time": "t1", "low": 90.0, "high": 95.0}, {"time": "t2", "low": 99.0, "high": 101.0}]
    out = naked_levels(levels, bars)
    assert out[0] == {"price": 100.0, "visible_from": "2026-10-06", "visible_until": "t2", "naked": False}
    assert out[1]["naked"] is True and out[1]["visible_until"] is None
    assert naked_levels([{"price": 1.0}], bars) == []

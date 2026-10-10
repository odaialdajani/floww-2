"""B23 profiles. Synthetic only."""
def test_poc_ties_down_and_va():
    from services.chart_profiles import poc, value_area
    rows = [{"price": 100, "volume": 10}, {"price": 101, "volume": 10}, {"price": 102, "volume": 5}]
    assert poc(rows)["price"] == 100
    va = value_area(rows, pct=0.70)
    assert va["status"] == "ok"
    assert va["low"] <= 100 <= va["high"]
    assert value_area([], 0.7)["status"] == "unavailable"

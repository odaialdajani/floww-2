"""B21 dark. Synthetic only."""
def test_levels():
    from services.chart_darkpool import top_levels
    prints = [
        {"price": 100.0, "size": 1000, "venue": "D", "event_time": 1, "asset_class": "equity"},
        {"price": 101.0, "size": 10, "venue": "D", "event_time": 2},
        {"price": 99.0, "size": 5, "venue": "D", "event_time": 3, "asset_class": "option"},
    ]
    out = top_levels(prints, top_n=2)
    assert len(out) == 2
    assert out[0]["price"] == 100.0
    assert out[0]["direction"] == "unknown"

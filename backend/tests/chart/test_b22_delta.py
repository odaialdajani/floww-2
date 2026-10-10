"""B22 delta. Synthetic only."""
def test_cvd():
    from services.chart_delta import session_cvd
    bars = [{"buy": 100, "sell": 40}, {"buy": 10, "sell": 20}, None, {"buy": 5, "sell": None}]
    out = session_cvd(bars)
    assert len(out) == 2
    assert out[0] == {"open": 0, "close": 60, "delta": 60, "unclassified": 0}
    assert out[1]["close"] == 50

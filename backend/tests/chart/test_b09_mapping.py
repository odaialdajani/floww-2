"""B09 mapping. Synthetic only."""
def test_ratio_ok_and_gates():
    from services.chart_mapping import derive_ratio
    s = {"price": 200.0, "known_at": "2026-10-06T14:00:00+00:00", "units": "USD"}
    t = {"price": 100.0, "known_at": "2026-10-06T14:00:00+00:00", "units": "USD"}
    assert derive_ratio(s, t)["ratio"] == 2.0
    assert derive_ratio(s, {"price": 0, "known_at": "x", "units": "USD"})["status"] == "unavailable"
    assert derive_ratio(s, {"price": 50.0, "known_at": "x", "units": "EUR"})["status"] == "unavailable"
    h = dict(s, historical=True)
    assert derive_ratio(h, t)["status"] == "unavailable"
    assert derive_ratio(dict(h, replay=True), dict(t, replay=True))["status"] == "available"

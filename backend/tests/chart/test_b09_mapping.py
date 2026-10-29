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


def test_v31_defect_gates():
    """H3 V31 defect pins: booleans are not numeric closes; non-finite refuses;
    a zero denominator is labeled honestly, never 'stale'."""
    from services.chart_mapping import derive_ratio
    s = {"price": 200.0, "known_at": "2026-10-06T14:00:00+00:00", "units": "USD"}
    t = {"price": 100.0, "known_at": "2026-10-06T14:00:00+00:00", "units": "USD"}
    # bool subclasses int: True must NOT pass as a close on either side
    assert derive_ratio(dict(s, price=True), t)["status"] == "unavailable"
    assert derive_ratio(s, dict(t, price=True))["status"] == "unavailable"
    # non-finite refuses on either side
    assert derive_ratio(dict(s, price=float("inf")), t)["status"] == "unavailable"
    assert derive_ratio(s, dict(t, price=float("nan")))["status"] == "unavailable"
    # a zero denominator is a ZERO denominator, never mislabeled 'stale'
    body = derive_ratio(s, {"price": 0, "known_at": "x", "units": "USD"})
    assert body["status"] == "unavailable"
    assert "zero" in body["reason"]

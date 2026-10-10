"""B15 replay algebra. Synthetic only."""
def test_known_at_and_age_and_partial():
    from services.chart_replay import age_ok, partial_bar, visible_snapshot
    snaps = [{"id": "a", "known_at": 100}, {"id": "b", "known_at": 90}]
    assert visible_snapshot(snaps, 95)["id"] == "b"
    assert visible_snapshot(snaps, 50) is None
    assert age_ok(0, 900) is True
    assert age_ok(0, 901) is False
    ev = [{"event_time": 10, "available_at": 10, "open": 1, "close": 2},
          {"event_time": 20, "available_at": 30, "open": 2, "close": 3}]
    out = partial_bar(ev, 25)
    assert out["close"] == 2 and out["complete"] is False
    assert partial_bar(ev, 5) is None

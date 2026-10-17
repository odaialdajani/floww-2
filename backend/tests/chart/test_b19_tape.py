"""B19 tape. Synthetic only."""
def test_print_and_commissioning():
    from services.chart_tape import commissioning, validate_print
    good = {"trade_id": "t1", "price": 100.0, "size": 10, "known_at": 5}
    assert validate_print(good)["status"] == "available"
    assert validate_print({})["status"] == "unavailable"
    assert validate_print({"trade_id": "t", "price": "x", "size": 1, "known_at": 1})["status"] == "unavailable"
    out = commissioning({})
    assert out == {"options_trades": "unavailable", "equity_trades": "unavailable", "dark_prints": "unavailable"}
    assert commissioning({"equity": True})["equity_trades"] == "available"

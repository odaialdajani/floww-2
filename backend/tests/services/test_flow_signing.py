"""A1: per-contract Lee-Ready signing (Agent A, institutional loop).

Quote rule on last-vs-NBBO at print time; tick test on mid drift as
fallback; crossed/locked/mid-print/degenerate inputs are UNKNOWN —
never a forced side. Tick-test lag is prev_mid (mid drift across sweeps).
"""

from services.flow_signing import aggressor_omega, sign_print, sign_snapshot


def test_quote_rule_above_mid_is_ask():
    assert sign_print(10.6, 10.0, 11.0) == ("ASK", "quote")


def test_quote_rule_below_mid_is_bid():
    assert sign_print(10.4, 10.0, 11.0) == ("BID", "quote")


def test_mid_print_falls_to_tick_up():
    assert sign_print(10.5, 10.0, 11.0, prev_mid=10.2) == ("ASK", "tick")


def test_mid_print_falls_to_tick_down():
    assert sign_print(10.5, 10.0, 11.0, prev_mid=10.8) == ("BID", "tick")


def test_mid_print_no_lag_is_unknown():
    assert sign_print(10.5, 10.0, 11.0) == ("UNKNOWN", "none")


def test_zero_tick_is_unknown():
    assert sign_print(10.5, 10.0, 11.0, prev_mid=10.5) == ("UNKNOWN", "none")


def test_crossed_quotes_are_unknown():
    assert sign_print(10.5, 11.0, 10.0) == ("UNKNOWN", "none")


def test_locked_quotes_are_unknown():
    assert sign_print(10.5, 10.5, 10.5) == ("UNKNOWN", "none")


def test_missing_quotes_tick_fallback():
    assert sign_print(10.5, None, 11.0, prev_mid=10.9) == ("BID", "tick")
    assert sign_print(10.5, None, None) == ("UNKNOWN", "none")


def test_missing_last_is_unknown():
    assert sign_print(None, 10.0, 11.0, prev_mid=10.2) == ("UNKNOWN", "none")


def test_snapshot_annotates_and_counts():
    rows = [
        {"last": 10.6, "bid": 10.0, "ask": 11.0},
        {"last": 10.4, "bid": 10.0, "ask": 11.0},
        {"last": 10.5, "bid": 10.0, "ask": 11.0},
    ]
    counts = sign_snapshot(rows)
    assert rows[0]["signed_side"] == "ASK"
    assert rows[1]["signed_side"] == "BID"
    assert rows[2]["signed_side"] == "UNKNOWN"
    assert counts == {"ASK": 1, "BID": 1, "UNKNOWN": 1}


def test_aggressor_omega_signed_share():
    rows = [
        {"signed_side": "ASK", "premium": 1000.0},
        {"signed_side": "BID", "premium": 500.0},
        {"signed_side": "UNKNOWN", "premium": 9000.0},
    ]
    assert aggressor_omega(rows) == 1 / 3


def test_aggressor_omega_no_signed_is_none():
    assert aggressor_omega([{"signed_side": "UNKNOWN", "premium": 5.0}]) is None
    assert aggressor_omega([]) is None

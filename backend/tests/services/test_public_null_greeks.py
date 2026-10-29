"""A missing optional Greeks object must not discard an otherwise usable quote."""

import pytest

from services.public_api import PublicBroker


@pytest.mark.parametrize(
    "details",
    [None, {}, {"greeks": None}, {"greeks": {}}],
)
def test_missing_greeks_preserve_quote_and_source_clocks(details):
    broker = PublicBroker.__new__(PublicBroker)
    contract = broker._parse_option_contract(
        {"symbol": "SPY261027C00770000"},
        {
            "bid": "1.00",
            "ask": "1.05",
            "bidTimestamp": "2026-10-27T19:00:00Z",
            "askTimestamp": "2026-10-27T19:00:01Z",
            "optionDetails": details,
        },
    )

    assert (contract.bid, contract.ask) == (1.0, 1.05)
    assert contract.bid_timestamp == "2026-10-27T19:00:00Z"
    assert contract.ask_timestamp == "2026-10-27T19:00:01Z"
    assert contract.last_timestamp is None
    assert contract.greeks_source is None
    assert all(
        getattr(contract, field) is None
        for field in ("iv", "delta", "gamma", "theta", "vega")
    )


def test_observed_zero_greek_remains_vendor_value_without_invented_clock():
    broker = PublicBroker.__new__(PublicBroker)
    contract = broker._parse_option_contract(
        {"symbol": "SPY261027C00770000"},
        {"optionDetails": {"greeks": {"delta": 0.0}}},
    )

    assert contract.delta == 0.0
    assert contract.gamma is None
    assert contract.greeks_source == "vendor"
    assert contract.last_timestamp is None

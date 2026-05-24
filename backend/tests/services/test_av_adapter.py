"""
Tests for services/av_adapter.py

Verifies:
- _safe_float / _safe_int NaN guards (I-8)
- normalize_quote handles standard, missing, and NaN-ridden payloads
- normalize_options_chain canonical shape
- Empty / degraded responses
"""

from __future__ import annotations

import math
import pytest
from datetime import datetime, timezone

from services.av_adapter import (
    _safe_float,
    _safe_int,
    normalize_quote,
    normalize_options_chain,
    fetch_and_normalize_chain,
    AV_DELAY_SECONDS,
)


# ── _safe_float ───────────────────────────────────────────────────────

class TestSafeFloat:
    def test_normal_value(self):
        assert _safe_float("123.45") == 123.45
        assert _safe_float(99.9) == 99.9
        assert _safe_float(0) == 0.0

    def test_none(self):
        assert _safe_float(None) is None
        assert _safe_float(None, 0.0) == 0.0

    def test_nan(self):
        assert _safe_float(float("nan")) is None
        assert _safe_float(math.nan) is None

    def test_inf(self):
        assert _safe_float(float("inf")) is None
        assert _safe_float(float("-inf")) is None

    def test_bad_strings(self):
        assert _safe_float("") is None
        assert _safe_float("N/A") is None
        assert _safe_float("--") is None


class TestSafeInt:
    def test_normal(self):
        assert _safe_int("42") == 42
        assert _safe_int(42.7) == 42

    def test_nan(self):
        assert _safe_int(math.nan) is None

    def test_none(self):
        assert _safe_int(None) is None


# ── normalize_quote ───────────────────────────────────────────────────

SAMPLE_QUOTE = {
    "Global Quote": {
        "01. symbol": "SPY",
        "02. open": "450.00",
        "03. high": "455.00",
        "04. low": "448.00",
        "05. price": "452.10",
        "06. volume": "12345678",
        "07. latest trading day": "2024-01-15",
        "08. previous close": "450.00",
        "09. change": "2.10",
        "10. change percent": "0.4667%",
    }
}


class TestNormalizeQuote:
    def test_standard_quote(self):
        result = normalize_quote(SAMPLE_QUOTE)
        assert result is not None
        assert result["price"] == 452.10
        assert result["open"] == 450.0
        assert result["high"] == 455.0
        assert result["low"] == 448.0
        assert result["volume"] == 12345678
        assert result["prev_close"] == 450.0
        assert result["change"] == 2.10
        assert result["change_pct"] == 0.4667
        assert result["source"] == "alphavantage"

    def test_price_zero(self):
        """Price <= 0 should return None."""
        q = {"Global Quote": {k: v for k, v in SAMPLE_QUOTE["Global Quote"].items()}}
        q["Global Quote"]["05. price"] = "0"
        assert normalize_quote(q) is None

    def test_price_nan(self):
        q = {"Global Quote": {k: v for k, v in SAMPLE_QUOTE["Global Quote"].items()}}
        q["Global Quote"]["05. price"] = "NaN"
        assert normalize_quote(q) is None

    def test_price_missing(self):
        assert normalize_quote({}) is None
        assert normalize_quote(None) is None

    def test_missing_fields(self):
        """Missing optional fields should not crash; price field required."""
        q = {"Global Quote": {"05. price": "100.00"}}
        result = normalize_quote(q)
        assert result is not None
        assert result["price"] == 100.0
        assert result["open"] is None
        # change_pct may be None when both change_percent and prev_close are missing
        # (both are optional fields — price is the only required one)
        assert "change_pct" in result

    def test_nan_in_fields(self):
        """NaN in volume/price fields guarded per I-8."""
        q = {"Global Quote": {k: v for k, v in SAMPLE_QUOTE["Global Quote"].items()}}
        q["Global Quote"]["06. volume"] = "NaN"
        result = normalize_quote(q)
        assert result["volume"] is None  # NaN → None

    def test_change_pct_parsing(self):
        """Change percent with trailing % or missing."""
        q = {"Global Quote": {k: v for k, v in SAMPLE_QUOTE["Global Quote"].items()}}
        q["Global Quote"]["10. change percent"] = "1.5%"
        result = normalize_quote(q)
        assert result["change_pct"] == 1.5

    def test_change_pct_fallback(self):
        """If change_pct missing, compute from price/prev_close."""
        q = {"Global Quote": {k: v for k, v in SAMPLE_QUOTE["Global Quote"].items()}}
        del q["Global Quote"]["10. change percent"]
        result = normalize_quote(q)
        assert result["change_pct"] is not None
        assert isinstance(result["change_pct"], float)


# ── normalize_options_chain ───────────────────────────────────────────

SAMPLE_CONTRACT = {
    "contractID": "SPY240119C00450000",
    "symbol": "SPY  240119C00450000",
    "type": "call",
    "strike": 450.0,
    "expiration": "2024-01-19",
    "bid": 3.45,
    "ask": 3.50,
    "last": 3.48,
    "volume": 1234,
    "open_interest": 56789,
    "implied_volatility": 0.185,
    "delta": 0.55,
    "gamma": 0.012,
    "theta": -0.08,
    "vega": 0.15,
}


class TestNormalizeOptionsChain:
    def test_empty_response(self):
        result = normalize_options_chain(None, 450.0)
        assert result["contract_count"] == 0
        assert result["contracts"] == []
        assert result["data_source"] == "alphavantage"
        assert result["delay_seconds"] == AV_DELAY_SECONDS

    def test_empty_data_array(self):
        result = normalize_options_chain({"data": []}, 450.0)
        assert result["contract_count"] == 0

    def test_single_contract(self):
        result = normalize_options_chain({"data": [SAMPLE_CONTRACT]}, spot_price=450.0)
        assert result["contract_count"] == 1
        c = result["contracts"][0]
        assert c["strike"] == 450.0
        assert c["type"] == "call"
        assert c["expiry"] == "2024-01-19"
        assert c["iv"] == 0.185
        assert c["delta"] == 0.55
        assert c["gamma"] == 0.012
        assert c["theta"] == -0.08
        assert c["vega"] == 0.15
        assert c["oi"] == 56789.0
        # GEX = gamma * spot * oi * 100
        expected_gex = 0.012 * 450.0 * 56789.0 * 100
        assert c["gex"] == pytest.approx(expected_gex)

    def test_contract_with_nan_greeks(self):
        """NaN in gamma/delta should not crash — guards per I-8."""
        contract = {k: v for k, v in SAMPLE_CONTRACT.items()}
        contract["gamma"] = float("nan")
        contract["delta"] = float("nan")
        result = normalize_options_chain({"data": [contract]}, spot_price=450.0)
        assert result["contract_count"] == 1
        c = result["contracts"][0]
        assert c["gamma"] is None
        assert c["delta"] is None
        assert c["gex"] is None  # gamma is None → gex is None

    def test_bad_contract_skip(self):
        """Invalid contracts (missing strike/expiry/type) should be skipped."""
        bad = {"type": "call"}  # no strike, no expiry
        result = normalize_options_chain({"data": [bad, SAMPLE_CONTRACT]}, 450.0)
        assert result["contract_count"] == 1

    def test_put_contract(self):
        contract = {k: v for k, v in SAMPLE_CONTRACT.items()}
        contract["type"] = "put"
        result = normalize_options_chain({"data": [contract]}, 450.0)
        assert result["contracts"][0]["type"] == "put"

    def test_invalid_type(self):
        contract = {k: v for k, v in SAMPLE_CONTRACT.items()}
        contract["type"] = "warrant"
        result = normalize_options_chain({"data": [contract]}, 450.0)
        assert result["contract_count"] == 0

    def test_T_computation(self):
        """T (years-to-expiry) should be non-negative float."""
        result = normalize_options_chain({"data": [SAMPLE_CONTRACT]}, 450.0)
        c = result["contracts"][0]
        assert c["T"] >= 0
        assert isinstance(c["T"], float)

    def test_av_response_uses_contracts_key(self):
        """Some AV responses use 'contracts' key instead of 'data'."""
        result = normalize_options_chain({"contracts": [SAMPLE_CONTRACT]}, 450.0)
        assert result["contract_count"] == 1

    def test_present_spot(self):
        result = normalize_options_chain({"data": [SAMPLE_CONTRACT]}, spot_price=455.50)
        assert result["spot"]["price"] == 455.50
        assert result["spot"]["source"] == "alphavantage"

    def test_missing_spot(self):
        result = normalize_options_chain({"data": [SAMPLE_CONTRACT]}, spot_price=None)
        assert result["spot"] is None


# ── fetch_and_normalize_chain (mock) ───────────────────────────────────

class MockAVProvider:
    """Duck-typed Alpha Vantage provider for testing."""

    def __init__(self, quote_result=None, chain_result=None):
        self._quote = quote_result
        self._chain = chain_result

    async def get_quote(self, ticker):
        return self._quote

    async def get_options_chain(self, ticker, num_expiries):
        return self._chain


@pytest.mark.asyncio
async def test_fetch_and_normalize_chain_happy():
    """Integration test: mock provider returns valid spot data.
    
    Note: AV free tier does not provide options chain data.
    The function fetches spot and returns an empty contracts list.
    """
    provider = MockAVProvider(
        quote_result={"price": 450.0, "change": 2.0, "change_pct": 0.44, "source": "alphavantage"},
        chain_result=None,  # AV has no chain endpoint on free tier
    )
    result = await fetch_and_normalize_chain("SPY", provider)
    assert result["spot"]["price"] == 450.0
    assert result["contract_count"] == 0  # AV free tier — no options chain


@pytest.mark.asyncio
async def test_fetch_and_normalize_chain_spot_failure():
    """Spot fetch fails — empty chain returned with no spot."""
    provider = MockAVProvider(quote_result=None, chain_result=None)
    result = await fetch_and_normalize_chain("SPY", provider)
    assert result["spot"] is None
    assert result["contract_count"] == 0


@pytest.mark.asyncio
async def test_fetch_and_normalize_chain_total_failure():
    """Both fail — empty chain returned."""
    provider = MockAVProvider(quote_result=None, chain_result=None)
    result = await fetch_and_normalize_chain("SPY", provider)
    assert result["spot"] is None
    assert result["contract_count"] == 0


@pytest.mark.asyncio
async def test_fetch_and_normalize_chain_exception():
    """Provider raises exception — should be caught gracefully."""

    class BrokenProvider:
        async def get_quote(self, ticker):
            raise RuntimeError("Network error")

    result = await fetch_and_normalize_chain("SPY", BrokenProvider())
    assert result["contract_count"] == 0

"""
backend/tests/services/test_flowseeker.py

Unit tests for services.flowseeker.

Coverage:
    * classify_print — happy paths for sweep / block / unusual / regular
    * classify_print — edge cases: missing fields, zero size, zero OI
    * fetch_live_flow — mocked FlashAlpha returns shape, min_premium filter,
      ticker filter, provider-failure resilience
    * contract_drilldown — mocked chain data returns expected fields

NO real network. All upstream calls are patched at
``services.flowseeker._get_client``.
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add backend/ to path so `services.flowseeker` is importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.flowseeker import (  # noqa: E402
    BLOCK_MIN_SIZE,
    SWEEP_MIN_SIZE,
    UNUSUAL_PREMIUM_USD,
    classify_print,
    contract_drilldown,
    fetch_live_flow,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client_mock(*, recent=None, live=None, outliers=None,
                     summary=None, history=None) -> MagicMock:
    """Build a MagicMock FlashAlphaClient with the right async coroutines."""
    client = MagicMock()
    client.get_options_flow_recent = AsyncMock(return_value=recent)
    client.get_flow_live = AsyncMock(return_value=live)
    client.get_options_flow_outliers = AsyncMock(return_value=outliers)
    client.get_options_flow_summary = AsyncMock(return_value=summary)
    client.get_options_flow_history = AsyncMock(return_value=history)
    return client


def _run(coro):
    """Run an async coroutine in tests without depending on pytest-asyncio."""
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


# ===========================================================================
# classify_print — happy paths
# ===========================================================================

class TestClassifyPrintHappy:
    def test_sweep_multi_exchange_within_window(self):
        """Multiple exchanges + size > 100 + time window <= 1s → sweep."""
        row = {
            "size": SWEEP_MIN_SIZE + 50,  # 150 > 100
            "exchanges": ["CBOE", "ISE", "PHLX"],
            "time_window_sec": 0.5,
            "premium": 25_000,
        }
        assert classify_print(row) == "sweep"

    def test_block_single_exchange_large_size(self):
        """Single exchange + size >= 500 → block."""
        row = {
            "size": BLOCK_MIN_SIZE,  # exactly 500
            "exchange": "CBOE",
            "premium": 50_000,
            "volume": 100,
            "oi": 1000,  # vol_oi_ratio = 0.1, well below unusual
        }
        assert classify_print(row) == "block"

    def test_unusual_high_vol_oi_ratio(self):
        """vol_oi_ratio > 2.0 with small size → unusual."""
        row = {
            "size": 10,  # not block-size
            "exchange": "CBOE",
            "volume": 250,
            "oi": 100,  # ratio = 2.5 > 2.0
            "premium": 5_000,
        }
        assert classify_print(row) == "unusual"

    def test_regular_small_print(self):
        """Small print on one exchange with normal vol/OI → regular."""
        row = {
            "size": 5,
            "exchange": "CBOE",
            "volume": 50,
            "oi": 1000,  # ratio = 0.05
            "premium": 1_000,
        }
        assert classify_print(row) == "regular"


# ===========================================================================
# classify_print — edge cases
# ===========================================================================

class TestClassifyPrintEdges:
    def test_missing_all_fields_is_regular(self):
        """An empty dict must not raise; default classification is regular."""
        assert classify_print({}) == "regular"

    def test_zero_size_is_regular(self):
        """size=0 disqualifies sweep and block; with no other signals → regular."""
        row = {
            "size": 0,
            "exchanges": ["CBOE", "ISE"],
            "time_window_sec": 0.5,
            "premium": 1_000,
        }
        assert classify_print(row) == "regular"

    def test_zero_oi_does_not_crash_division(self):
        """oi=0 must not raise ZeroDivisionError; vol_oi_ratio falls back to 0."""
        row = {
            "size": 5,
            "exchange": "CBOE",
            "volume": 500,
            "oi": 0,  # divisor guard
            "premium": 1_000,
        }
        # With ratio forced to 0 and premium below $100k, this is regular.
        assert classify_print(row) == "regular"

    def test_unusual_via_premium_alone(self):
        """premium > $100k forces unusual even with low vol/OI ratio."""
        row = {
            "size": 5,
            "exchange": "CBOE",
            "volume": 5,
            "oi": 1000,  # ratio ≈ 0
            "premium": UNUSUAL_PREMIUM_USD + 1,  # 100,001
        }
        assert classify_print(row) == "unusual"

    def test_sweep_precedence_over_block(self):
        """Order matters: a 600-size multi-exchange print is sweep, not block."""
        row = {
            "size": 600,  # also block-eligible by size
            "exchanges": ["CBOE", "ISE"],
            "time_window_sec": 0.2,
            "premium": 200_000,  # also unusual-eligible
        }
        assert classify_print(row) == "sweep"

    def test_non_dict_input_returns_regular(self):
        """Defensive — list / string / None must not raise."""
        assert classify_print(None) == "regular"  # type: ignore[arg-type]
        assert classify_print("garbage") == "regular"  # type: ignore[arg-type]


# ===========================================================================
# fetch_live_flow — provider integration via mocked client
# ===========================================================================

class TestFetchLiveFlow:
    def test_returns_20_column_shape_for_each_print(self):
        """The 20-column Flowseeker shape must be present on every row."""
        raw_payload = {
            "prints": [
                {
                    "timestamp": "2025-01-15T15:30:00Z",
                    "ticker": "SPY",
                    "strike": 470.0,
                    "expiration": "2025-02-21",
                    "side": "BUY",
                    "type": "C",
                    "size": 200,
                    "price": 2.50,
                    "premium": 50_000,
                    "volume": 1500,
                    "oi": 2000,
                    "vol_oi_ratio": 0.75,
                    "chain_ratio": 1.2,
                    "conditions": ["A", "I"],
                    "ask_pct": 0.85,
                    "spot": 472.0,
                    "bid": 2.45,
                    "ask": 2.55,
                    "exchange": "CBOE",
                },
            ]
        }
        client = _make_client_mock(recent=raw_payload)
        with patch("services.flowseeker._get_client", return_value=client):
            out = _run(fetch_live_flow(ticker="SPY"))
        assert len(out) == 1
        row = out[0]
        expected_keys = {
            "timestamp", "ticker", "strike", "expiration", "side", "type",
            "size", "price", "premium", "volume", "oi", "vol_oi_ratio",
            "chain_ratio", "classification", "conditions", "ask_pct",
            "spot", "bid", "ask", "exchange",
        }
        assert expected_keys.issubset(row.keys())
        assert row["ticker"] == "SPY"
        assert row["classification"] == "regular"  # single exchange, size<500, ratio<2

    def test_falls_back_to_live_when_recent_returns_none(self):
        """If get_options_flow_recent yields None, fall back to get_flow_live."""
        live_payload = {
            "data": [
                {"ticker": "QQQ", "size": 50, "premium": 5000, "exchange": "CBOE"},
            ]
        }
        client = _make_client_mock(recent=None, live=live_payload)
        with patch("services.flowseeker._get_client", return_value=client):
            out = _run(fetch_live_flow(ticker="QQQ"))
        assert len(out) == 1
        assert out[0]["ticker"] == "QQQ"
        client.get_options_flow_recent.assert_awaited_once()
        client.get_flow_live.assert_awaited_once()

    def test_filters_by_min_premium(self):
        """Rows with premium below min_premium must be excluded."""
        payload = {
            "prints": [
                {"ticker": "SPY", "size": 5, "premium": 500, "exchange": "CBOE"},
                {"ticker": "SPY", "size": 5, "premium": 10_000, "exchange": "CBOE"},
                {"ticker": "SPY", "size": 5, "premium": 100_000, "exchange": "CBOE"},
            ]
        }
        client = _make_client_mock(recent=payload)
        with patch("services.flowseeker._get_client", return_value=client):
            out = _run(fetch_live_flow(ticker="SPY", min_premium=5_000))
        # 500 excluded, 10_000 and 100_000 included
        assert len(out) == 2
        assert all(r["premium"] >= 5_000 for r in out)

    def test_filters_by_ticker_when_upstream_returns_mixed(self):
        """When ticker is given, foreign-ticker prints must be excluded."""
        payload = {
            "prints": [
                {"ticker": "SPY", "size": 5, "premium": 1000, "exchange": "CBOE"},
                {"ticker": "QQQ", "size": 5, "premium": 1000, "exchange": "CBOE"},
                {"ticker": "SPY", "size": 10, "premium": 2000, "exchange": "CBOE"},
            ]
        }
        client = _make_client_mock(recent=payload)
        with patch("services.flowseeker._get_client", return_value=client):
            out = _run(fetch_live_flow(ticker="SPY"))
        assert len(out) == 2
        assert all(r["ticker"] == "SPY" for r in out)

    def test_provider_failure_returns_empty_list(self):
        """If FlashAlpha returns None, function returns [] (no crash)."""
        client = _make_client_mock(recent=None, live=None)
        with patch("services.flowseeker._get_client", return_value=client):
            out = _run(fetch_live_flow(ticker="SPY"))
        assert out == []

    def test_no_ticker_uses_outliers_endpoint(self):
        """When ticker is None, the cross-ticker outliers endpoint is used."""
        outliers = {
            "results": [
                {"ticker": "TSLA", "size": 10, "premium": 1000, "exchange": "CBOE"},
            ]
        }
        client = _make_client_mock(outliers=outliers)
        with patch("services.flowseeker._get_client", return_value=client):
            out = _run(fetch_live_flow(ticker=None))
        assert len(out) == 1
        assert out[0]["ticker"] == "TSLA"
        client.get_options_flow_outliers.assert_awaited_once()


# ===========================================================================
# contract_drilldown — mocked chain data
# ===========================================================================

class TestContractDrilldown:
    def test_returns_expected_fields_with_full_payload(self):
        """Drilldown payload must surface volume, oi, chain_ratio, prints, history."""
        recent_payload = {
            "prints": [
                {"ticker": "SPY", "size": 10, "premium": 1000, "exchange": "CBOE"},
            ]
        }
        summary_payload = {
            "total_volume": 50_000,
            "total_oi": 100_000,
            "chain_ratio": 1.5,
        }
        history_payload = {
            "history": [
                {"volume": 1000, "oi": 500},  # ratio 2.0
                {"volume": 2000, "oi": 500},  # ratio 4.0
                0.75,  # raw float entry — must be tolerated
            ]
        }
        client = _make_client_mock(
            recent=recent_payload,
            summary=summary_payload,
            history=history_payload,
        )
        with patch("services.flowseeker._get_client", return_value=client):
            out = _run(contract_drilldown("SPY"))
        assert out["symbol"] == "SPY"
        assert out["volume"] == 50_000
        assert out["oi"] == 100_000
        assert out["chain_ratio"] == 1.5
        assert len(out["recent_prints"]) == 1
        assert out["recent_prints"][0]["ticker"] == "SPY"
        # 3 history entries, two dict-derived and one raw float
        assert len(out["vol_oi_history"]) == 3
        assert out["vol_oi_history"][0] == pytest.approx(2.0)
        assert out["vol_oi_history"][1] == pytest.approx(4.0)
        assert out["vol_oi_history"][2] == pytest.approx(0.75)

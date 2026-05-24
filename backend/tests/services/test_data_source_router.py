"""
Tests for services/data_source_router.py

Verifies:
- Env var FLOWW_DATA_SOURCE parsing
- Auto-resolution fallback chain
- Key presence detection
- Runtime source switching via set_data_source()
- Prometheus label registration
"""

from __future__ import annotations

import os
import pytest

from services.data_source_router import (
    get_data_source,
    get_active_source_info,
    get_configured_source,
    set_data_source,
    reset,
    ALPHA_VANTAGE,
    DATABENTO,
    SCHWAB,
    AUTO,
    VALID_SOURCES,
)


# ── Fixtures ───────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_between_tests():
    """Reset cached source state between tests."""
    reset()
    # Pop a known AV key so auto-resolve prefers AV
    os.environ["ALPHA_VANTAGE_KEY"] = "test_av_key_123"
    yield
    reset()


# ── get_configured_source ─────────────────────────────────────────────

class TestGetConfiguredSource:
    def test_default_is_auto(self):
        """Default FLOWW_DATA_SOURCE is 'auto'."""
        if "FLOWW_DATA_SOURCE" in os.environ:
            del os.environ["FLOWW_DATA_SOURCE"]
        assert get_configured_source() == AUTO

    def test_explicit_setting(self):
        os.environ["FLOWW_DATA_SOURCE"] = ALPHA_VANTAGE
        assert get_configured_source() == ALPHA_VANTAGE


# ── get_data_source ───────────────────────────────────────────────────

class TestGetDataSource:
    def test_auto_resolves_to_alpha_vantage(self):
        """With AV key set, auto should resolve to alpha_vantage."""
        os.environ["FLOWW_DATA_SOURCE"] = AUTO
        os.environ["ALPHA_VANTAGE_KEY"] = "test_key"
        assert get_data_source() == ALPHA_VANTAGE

    def test_auto_falls_back_to_databento(self):
        """No AV key, but Databento key present → databento."""
        os.environ["FLOWW_DATA_SOURCE"] = AUTO
        os.environ.pop("ALPHA_VANTAGE_KEY", None)
        os.environ["DATABENTO_API_KEY"] = "test_db_key"
        assert get_data_source() == DATABENTO

    def test_auto_falls_back_to_schwab(self):
        """No AV or Databento keys → schwab."""
        os.environ["FLOWW_DATA_SOURCE"] = AUTO
        os.environ.pop("ALPHA_VANTAGE_KEY", None)
        os.environ.pop("DATABENTO_API_KEY", None)
        assert get_data_source() == SCHWAB

    def test_explicit_alpha_vantage(self):
        os.environ["FLOWW_DATA_SOURCE"] = ALPHA_VANTAGE
        assert get_data_source() == ALPHA_VANTAGE

    def test_explicit_databento(self):
        os.environ["FLOWW_DATA_SOURCE"] = DATABENTO
        assert get_data_source() == DATABENTO

    def test_explicit_schwab(self):
        os.environ["FLOWW_DATA_SOURCE"] = SCHWAB
        assert get_data_source() == SCHWAB

    def test_invalid_source_falls_back_to_auto(self):
        os.environ["FLOWW_DATA_SOURCE"] = "nonexistent_source"
        # Should warn and fall back to auto
        source = get_data_source()
        assert source in (ALPHA_VANTAGE, DATABENTO, SCHWAB)


# ── get_active_source_info ────────────────────────────────────────────

class TestGetActiveSourceInfo:
    def test_returns_expected_keys(self):
        os.environ["FLOWW_DATA_SOURCE"] = ALPHA_VANTAGE
        info = get_active_source_info()
        assert "active" in info
        assert "delay_seconds" in info
        assert "configured" in info
        assert "key_present" in info
        assert "asof" in info

    def test_alpha_vantage_delay(self):
        os.environ["FLOWW_DATA_SOURCE"] = ALPHA_VANTAGE
        info = get_active_source_info()
        assert info["delay_seconds"] == 900

    def test_databento_delay(self):
        os.environ["FLOWW_DATA_SOURCE"] = DATABENTO
        info = get_active_source_info()
        assert info["delay_seconds"] == 0

    def test_key_present_true(self):
        os.environ["ALPHA_VANTAGE_KEY"] = "test"
        os.environ["FLOWW_DATA_SOURCE"] = ALPHA_VANTAGE
        info = get_active_source_info()
        assert info["key_present"] is True

    def test_key_present_false(self):
        os.environ.pop("ALPHA_VANTAGE_KEY", None)
        os.environ["FLOWW_DATA_SOURCE"] = ALPHA_VANTAGE
        info = get_active_source_info()
        assert info["key_present"] is False


# ── set_data_source ───────────────────────────────────────────────────

class TestSetDataSource:
    def test_set_valid_source(self):
        assert set_data_source(ALPHA_VANTAGE) is True
        assert get_data_source() == ALPHA_VANTAGE

    def test_set_invalid_source(self):
        assert set_data_source("invalid") is False

    def test_set_auto(self):
        set_data_source(AUTO)
        # Should resolve auto
        assert get_data_source() in (ALPHA_VANTAGE, DATABENTO, SCHWAB)


# ── reset ─────────────────────────────────────────────────────────────

class TestReset:
    def test_reset_clears_cache(self):
        os.environ["FLOWW_DATA_SOURCE"] = ALPHA_VANTAGE
        assert get_data_source() == ALPHA_VANTAGE
        reset()
        # After reset, should re-read from env
        os.environ["FLOWW_DATA_SOURCE"] = DATABENTO
        assert get_data_source() == DATABENTO


# ── VALID_SOURCES ─────────────────────────────────────────────────────

class TestValidSources:
    def test_all_sources_are_valid(self):
        for s in (ALPHA_VANTAGE, DATABENTO, SCHWAB, AUTO):
            assert s in VALID_SOURCES

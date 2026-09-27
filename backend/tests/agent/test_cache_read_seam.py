import pytest

from services.fetch_coordinator import CacheRouter


def test_cache_peek_does_not_fetch_or_mutate():
    cache = CacheRouter()
    assert cache.peek_chain("SPY", 6) is None
    cache._cache["chain:SPY:6"] = {"ts": 0, "data": {"spot": 123, "contracts": [{"strike": 120}], "fetched_at": None}}
    data = cache.peek_chain("SPY", 6)
    data["contracts"][0]["strike"] = 999
    assert cache.peek_chain("SPY", 6)["contracts"][0]["strike"] == 120
    assert cache.peek_chain("SPY", 4) is None
    assert data["fetched_at"] is None
    assert data["cache_age_s"] > 0


def test_default_dashboard_cache_can_be_read_with_explicit_coverage():
    cache = CacheRouter()
    cache._cache["chain:SPY:4"] = {"ts": 0, "data": {"spot": 123, "contracts": []}}
    data = cache.peek_available_chain("SPY", 6)
    assert data["spot"] == 123
    assert data["requested_expiry_count"] == 4

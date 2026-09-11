"""D7 — issue #18 additive contract-shape parity.

Base route GET /api/contract/{ticker} rows must carry the same additive
keys as the strike route (last/open_interest/midpoint/osi), computed by
one shared mapping helper, without removing any prior key/value.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from server import app

client = TestClient(app)

CHAIN = {
    "ticker": "SPY",
    "spot": 500.0,
    "spot_source": "test",
    "contracts": [
        {
            "type": "call", "strike": 500.0, "expiry": "2026-09-18",
            "iv": 0.20, "delta": 0.55, "gamma": 0.01, "vega": 0.5,
            "theta": -0.1, "oi": 1200, "volume": 88,
            "bid": 2.0, "ask": 2.4, "midpoint": 2.2,
            "osi": "SPY260918C00500000",
        },
        {
            "type": "put", "strike": 500.0, "expiry": "2026-09-18",
            "iv": 0.22, "delta": -0.45, "gamma": 0.011, "vega": 0.5,
            "theta": -0.1, "oi": 3400, "volume": 12,
            "bid": 0.0, "ask": 1.5, "midpoint": 0.0,
        },
    ],
}

PRIOR_BASE_KEYS = {
    "type", "strike", "expiry", "iv", "delta", "gamma", "vega",
    "theta", "oi", "volume", "bid", "ask", "gex",
}


def _base_rows():
    with patch(
        "routes.analytics._cache.get_chain",
        new=AsyncMock(return_value=CHAIN),
    ):
        r = client.get("/api/contract/SPY")
    assert r.status_code == 200, r.text
    return r.json()["rows"]


def test_base_rows_gain_additive_keys():
    rows = _base_rows()
    assert len(rows) == 2
    for row in rows:
        # every prior key retained ...
        assert set(row.keys()) >= PRIOR_BASE_KEYS, sorted(row.keys())
        # ... plus additive parity keys
        for key in ("last", "open_interest", "midpoint", "osi"):
            assert key in row, sorted(row.keys())


def test_base_rows_mirror_strike_values():
    rows = _base_rows()
    with patch(
        "routes.analytics._cache.get_chain",
        new=AsyncMock(return_value=CHAIN),
    ):
        r = client.get("/api/contract/SPY/500.0/2026-09-18")
    assert r.status_code == 200, r.text
    strike_contracts = r.json()["contracts"]
    assert len(strike_contracts) == 2
    for base in rows:
        match = next(
            c for c in strike_contracts if c["type"] == base["type"]
        )
        for key in (
            "type", "strike", "expiry", "iv", "delta", "bid", "ask",
            "last", "midpoint", "open_interest", "oi", "volume", "osi",
        ):
            assert base[key] == match[key], (key, base[key], match[key])


def test_last_fallback_rules():
    rows = _base_rows()
    call = next(r for r in rows if r["type"] == "call")
    put = next(r for r in rows if r["type"] == "put")
    # positive midpoint wins
    assert call["last"] == 2.2
    # midpoint 0 + one-sided (bid 0) -> surviving side
    assert put["last"] == 1.5
    # open_interest mirrors oi; unknown osi is null
    assert call["open_interest"] == call["oi"] == 1200
    assert call["osi"] == "SPY260918C00500000"
    assert put["osi"] is None


def test_shared_mapping_helper():
    from routes import analytics

    assert callable(getattr(analytics, "_map_contract_leg", None))
    rows = [
        {
            "type": "call", "strike": 500.0, "expiry": "2026-09-18",
            "iv": 0.2, "delta": 0.5, "bid": 2.0, "ask": 2.4,
            "midpoint": 2.2, "oi": 10, "volume": 1,
        }
    ]
    direct = analytics._map_contract_leg(rows[0])
    via_strike = analytics.contracts_for_strike_expiry(
        rows, 500.0, "2026-09-18"
    )
    assert len(via_strike) == 1
    for key in (
        "type", "strike", "expiry", "iv", "delta", "bid", "ask",
        "last", "midpoint", "open_interest", "oi", "volume", "osi",
    ):
        assert via_strike[0][key] == direct[key], key

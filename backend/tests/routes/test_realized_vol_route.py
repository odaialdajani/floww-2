"""
backend/tests/routes/test_realized_vol_route.py

Integration TestClient for ``GET /api/vol/realized/{ticker}`` mounted in
``backend/routes/steal_three.py`` for steal-list #7 (RV/VRP).

End-to-end suite that monkeypatches yfinance, the existing ``_load_chain``
helper, and ``services.duckdb_engine.db`` so the route executes fully
offline with no Mongo / yfinance / network I/O. Pattern mirrors
``backend/tests/routes/test_flowseeker_scan.py``.

3 cases:
       1. Successful shape contract — required keys present, all 5
          estimators computed, VRP label valid.
       2. accumulate=true writes at least one row to the stubbed
          DuckDB engine (cron-write path mirror of max_pain_drift /
          consensus_drift / occ_volume).
       3. Defensive degrade — yfinance crashing returns 200 (NOT 500)
          with empty shape + an ``engine exception`` warning.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.steal_three import router as steal_three_router


@pytest.fixture(autouse=True)
def _pin_legacy_provider_env(monkeypatch):
    """These three cases document the legacy market-data contract: yfinance
    OHLC + chain loading, the DuckDB accumulate path and the defensive-degrade
    warning. ADR-0002 keeps that path code-active only when
    ``FLOWW_MARKET_DATA_PROVIDER != "public"``; host checkouts may set the
    variable to ``public`` (then the shared guard refuses legacy studies with
    503 before any of this logic runs). Pin the documented mode so the
    contract stays hermetic regardless of host ``.env`` state. Public-only
    refusal for this route is covered by policy tests, not re-hidden here."""
    monkeypatch.delenv("FLOWW_MARKET_DATA_PROVIDER", raising=False)


# ─────────────────────────────────────────────────────────────────────
# Test app + FakeYFTicker (60d of stable OHLC; enough bars for 60d cone
# + 21d typical-range-band lookbacks).
# ─────────────────────────────────────────────────────────────────────

app = FastAPI()
app.include_router(steal_three_router)
client = TestClient(app)


_ESTIMATOR_NAMES = (
    "yang_zhang", "garman_klass", "parkinson",
    "rogers_satchell", "close_to_close",
)


class _FakeYFTicker:
    """Returns a 60-day OHLC history with stable close ~100 + small drift."""

    def __init__(self, *args, **kwargs):
        pass

    def history(self, *args, **kwargs):
        n = 60
        idx = pd.date_range(end="2026-07-17", periods=n, freq="D")
        closes = [
            100.0 * math.exp(0.01 * math.sin(i / 5.0) + 0.001 * i)
            for i in range(n)
        ]
        opens = [c * 0.995 for c in closes]
        highs = [max(o, c) * 1.01 for o, c in zip(opens, closes, strict=False)]
        lows = [min(o, c) * 0.99 for o, c in zip(opens, closes, strict=False)]
        return pd.DataFrame(
            {"Open": opens, "High": highs, "Low": lows, "Close": closes},
            index=idx,
        )


class _FakeDuckEngine:
    """Record-only stand-in for services.duckdb_engine.db."""

    def __init__(self) -> None:
        self.writes = 0
        self.queries = 0

    def execute_write(self, sql: str, params=None) -> None:
        self.writes += 1

    def query(self, sql: str, params=None):
        self.queries += 1
        return []


@pytest.fixture(autouse=True)
def _isolate_route(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub yfinance + duckdb + _load_chain so the route runs offline."""
    monkeypatch.setattr("yfinance.Ticker", _FakeYFTicker)
    monkeypatch.setattr(
        "routes.steal_three._load_chain",
        lambda *args, **kwargs: (
            102.0,
            [{"strike": 102.0, "impliedVolatility": 0.25}],
            [],
            "2026-07-17",
        ),
    )
    import services.duckdb_engine as db_mod
    monkeypatch.setattr(db_mod, "db", _FakeDuckEngine())


# ─────────────────────────────────────────────────────────────────────
# Cases
# ─────────────────────────────────────────────────────────────────────


def test_vol_realized_returns_200_and_full_shape_contract() -> None:
    """Default ``accumulate=false`` returns 200 with the 9-key shape."""
    res = client.get("/api/vol/realized/SPY")
    assert res.status_code == 200

    data = res.json()
    assert data["ticker"] == "SPY"
    assert data["source"] == "steal-three-router"
    assert isinstance(data.get("spot"), (int, float))
    assert isinstance(data.get("front_atm_iv"), (int, float))
    assert isinstance(data.get("estimators"), dict)
    for est in _ESTIMATOR_NAMES:
        assert est in data["estimators"], (
            f"missing estimator {est!r} in response"
        )

    # VRP shape — atm_iv, yz_rv, ratio, spread, label
    vrp = data["vrp"]
    assert "vrp_ratio" in vrp
    assert "vrp_spread" in vrp
    assert "vrp_label" in vrp
    assert vrp["vrp_label"] in {
        "short_vol_favored", "long_vol_favored", "fair", "undefined",
    }

    # Cone + bands — must at least be present (type-loose on content)
    assert "cones" in data
    assert "typical_range_bands" in data
    assert "history" in data
    assert "warnings" in data
    assert isinstance(data["history"], list)


def test_vol_realized_accumulate_triggers_duckdb_write() -> None:
    """``accumulate=true`` with a finite YZ value writes to duckdb at least once."""
    res = client.get("/api/vol/realized/QCOM?accumulate=true")
    assert res.status_code == 200
    # The monkeypatched db still records writes in-memory; verify via direct attr.
    import services.duckdb_engine as db_mod
    assert db_mod.db.writes >= 1, (
        "accumulate=true must trigger at least one execute_write"
    )


def test_vol_realized_defensive_degrade_on_yfinance_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Yfinance crashing MUST NOT 500; route returns 200 with empty shape."""
    def _boom(*args, **kwargs):
        raise RuntimeError("yfinance down")

    monkeypatch.setattr("yfinance.Ticker", _boom)

    res = client.get("/api/vol/realized/CRASH")
    assert res.status_code == 200  # never 500s
    data = res.json()
    assert data["ticker"] == "CRASH"
    assert data["spot"] is None
    assert data["front_atm_iv"] is None
    for est in _ESTIMATOR_NAMES:
        assert data["estimators"][est] is None
    assert data["vrp"]["vrp_label"] == "undefined"
    assert any("engine exception" in w for w in data["warnings"])

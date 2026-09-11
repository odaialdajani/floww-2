"""
Regression tests for the 2026-09-03 Solstice open-universe + Meridian fixes.

  * Dual-GEX (#1): per-row gamma from the numba Black-Scholes pipeline
    (no more flat gamma=1.0 fallback as the primary path).
  * IV-Mid (#5): honest invalid_reason codes (zero_mid / below_intrinsic /
    degenerate_expiry / solve_failed) + real dte_days + T-floor so 1-DTE
    rows can solve.
  * Wheel (#3): 30s TTL cache on _run_income_screener (second identical
    call served from cache, loader hit once) — kills the Yahoo scrape
    storm behind the dashboard 429s.

All network boundaries are mocked; no live calls.
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_minimal_app():
    from routes.steal_three import router as steal_three_router
    app = FastAPI(title="steal-three open-universe")
    app.include_router(steal_three_router)
    return app


def _future_exp(days: int = 21) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


# ---------------------------------------------------------------------------
# Dual-GEX: real gamma
# ---------------------------------------------------------------------------

def test_dual_gex_uses_numba_gamma_not_flat(monkeypatch):
    calls = [{"strike": 100.0, "openInterest": 10, "volume": 5.0,
              "bid": 1.0, "ask": 1.2, "impliedVolatility": 0.25,
              "expiry": _future_exp()}]
    puts = [{"strike": 90.0, "openInterest": 20, "volume": 2.0,
             "bid": 0.8, "ask": 1.0, "impliedVolatility": 0.30,
             "expiry": _future_exp()}]
    monkeypatch.setattr(
        "routes.steal_three._load_chain",
        lambda ticker, expiry_index=0, min_dte=0: (100.0, calls, puts, _future_exp()),
    )
    client = TestClient(_build_minimal_app())
    resp = client.get("/api/dual_gex/SPY")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["gamma_model"] == "numba_bs"
    assert "defaulted to 1.0" not in data["note"]
    assert sorted(data["strikes"]) == [90.0, 100.0]


def test_dual_gex_survives_rows_without_iv(monkeypatch):
    # Bare rows (no IV, no parseable expiry) fall back to IV=0.2 / T=30d
    # inside the gamma computation — never a 500.
    calls = [{"strike": 100.0, "openInterest": 10, "volume": 5.0,
              "bid": 1.0, "ask": 1.2, "expiry": "garbage"}]
    puts = [{"strike": 90.0, "openInterest": 20, "volume": 2.0,
             "bid": 0.8, "ask": 1.0, "expiry": "garbage"}]
    monkeypatch.setattr(
        "routes.steal_three._load_chain",
        lambda ticker, expiry_index=0, min_dte=0: (100.0, calls, puts, "garbage"),
    )
    client = TestClient(_build_minimal_app())
    resp = client.get("/api/dual_gex/SPY")
    assert resp.status_code == 200, resp.text
    assert sorted(resp.json()["strikes"]) == [90.0, 100.0]


# ---------------------------------------------------------------------------
# IV-Mid: reason codes
# ---------------------------------------------------------------------------

def test_iv_row_zero_mid_reason():
    from routes.steal_three import _iv_row
    row = {"strike": 100.0, "bid": 0.0, "ask": 0.0,
           "lastPrice": 0.0, "impliedVolatility": 0.22}
    r = _iv_row(row, 100.0, 30 / 365, "call", 30)
    assert r["solved_iv_is_invalid"] is True
    assert r["invalid_reason"] == "zero_mid"
    assert r["dte_days"] == 30
    assert type(r["solved_iv_is_invalid"]) is bool


def test_iv_row_below_intrinsic_reason():
    from routes.steal_three import _iv_row
    # Deep ITM call quoted below parity — no IV exists; must say so.
    row = {"strike": 90.0, "bid": 9.0, "ask": 9.2,
           "lastPrice": 9.1, "impliedVolatility": 0.25}
    r = _iv_row(row, 100.0, 30 / 365, "call", 30)
    assert r["solved_iv_is_invalid"] is True
    assert r["invalid_reason"] == "below_intrinsic"


def test_iv_row_valid_atm_solves():
    from routes.steal_three import _iv_row
    row = {"strike": 100.0, "bid": 4.8, "ask": 5.2,
           "lastPrice": 5.0, "impliedVolatility": 0.22}
    r = _iv_row(row, 100.0, 30 / 365, "call", 30)
    assert r["invalid_reason"] is None
    assert r["solved_iv"] > 0
    assert r["solved_iv_is_invalid"] is False
    assert r["dte_days"] == 30


def test_iv_row_short_dated_can_solve_with_t_floor():
    from routes.steal_three import _iv_row
    # 1-DTE ATM call: vega dust at raw T, solvable at the 2-day floor.
    row = {"strike": 100.0, "bid": 1.2, "ask": 1.4,
           "lastPrice": 1.3, "impliedVolatility": 0.20}
    r = _iv_row(row, 100.0, 1 / 365, "call", 1)
    assert r["solved_iv"] > 0
    assert r["invalid_reason"] is None


# ---------------------------------------------------------------------------
# Wheel: TTL cache
# ---------------------------------------------------------------------------

def test_wheel_screener_caches_identical_calls(monkeypatch):
    import routes.steal_three as st

    st._income_cache.clear()
    future_exp = _future_exp()
    put_row = {"strike": 95.0, "expiry": future_exp, "openInterest": 500,
               "volume": 40, "bid": 1.0, "ask": 1.2, "impliedVolatility": 0.25}
    call_row = {"strike": 105.0, "expiry": future_exp, "openInterest": 300,
                "volume": 30, "bid": 0.9, "ask": 1.1, "impliedVolatility": 0.22}
    calls = {"n": 0}

    def fake_window(symbol, min_dte, max_dte, cap=8):
        calls["n"] += 1
        return (100.0, [call_row], [put_row])

    monkeypatch.setattr("routes.steal_three._load_chain_window", fake_window)
    client = TestClient(_build_minimal_app())
    params = {"symbol": "HOOD", "side": "both", "min_dte": 7, "max_dte": 45}
    r1 = client.get("/api/screener/income", params=params)
    assert r1.status_code == 200, r1.text
    assert r1.json()["cached"] is False
    r2 = client.get("/api/screener/income", params=params)
    assert r2.status_code == 200, r2.text
    assert r2.json()["cached"] is True
    assert calls["n"] == 1
    assert r1.json()["puts"] == r2.json()["puts"]
    st._income_cache.clear()


# ---------------------------------------------------------------------------
# build_heatmap strike volumes (Profile view volume column)
# ---------------------------------------------------------------------------

def test_attach_strike_volumes_rolls_calls_and_puts():
    from server import _attach_strike_volumes
    strikes = [{"strike": 100.0}, {"strike": 90.0}, {"strike": 80.0}]
    contracts = [
        {"strike": 100.0, "type": "call", "volume": 10},
        {"strike": 100.0, "type": "put", "volume": 5},
        {"strike": 90.0, "type": "call", "vol": 7},
        {"strike": 90.0, "type": "call", "volume": 0},   # skipped
        {"strike": None, "type": "call", "volume": 99},  # skipped
    ]
    _attach_strike_volumes(strikes, contracts)
    assert strikes[0]["total_volume"] == 15.0
    assert strikes[0]["call_volume"] == 10.0
    assert strikes[0]["put_volume"] == 5.0
    assert strikes[1]["total_volume"] == 7.0
    assert strikes[2]["total_volume"] == 0.0

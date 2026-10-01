"""R11 H01 — metric display contract, proven through the real builder.

Fixture (independently computed, not copied from any screenshot):
  spot S = 100, multiplier m = 100, gamma Γ = 0.1  ->  u = Γ·m·S²·0.01 = 1000
  call @100:  OI 100, V 10, δ 0.5
     raw OI                Σ c·u·N         = 100,000
     Δ-weighted OI         Σ c·u·N·|δ|     =  50,000
     session volume        Σ c·u·V         =  10,000   (legacy `activity`)
     session volume × |Δ|  Σ c·u·V·|δ|     =   5,000
  put  @105:  OI 100, V 10, δ missing  -> raw −100,000; Δ surfaces UNKNOWN
  call @95 :  OI 50,  V 4,  δ 0.25     -> fills a second strike

All values must come out of `server._build_heatmap_impl` (the function both
`/api/heatmap` and `/api/data` call) with the provider fetch replaced by the
fixture and the offline guard active, so any real Public/AI connection fails.
"""
from __future__ import annotations

import asyncio as _asyncio
import math
from unittest.mock import AsyncMock, patch

import pytest

import server
import services.cvserver_client as cvmod
from services.solstice_enrichment import window_contract_activity
from tests.offline_network import deny_external_network  # noqa: F401

_LOOP = _asyncio.new_event_loop()
EXP = "2031-01-17"
TICKER = "R11FX"


def _c(strike, typ, oi, vol, delta, **extra):
    return {"strike": float(strike), "expiry": EXP, "T": 30 / 365.0, "type": typ,
            "oi": float(oi), "volume": float(vol), "gamma": 0.1, "delta": delta,
            "iv": 0.25, "theta": -0.02, "vega": 0.1,
            "bid": 1.0, "ask": 1.1, "mid": 1.05, "last": 1.05, **extra}


FIXTURE_CONTRACTS = [
    _c(100, "call", 100, 10, 0.5),
    _c(105, "put", 100, 10, None),
    _c(95, "call", 50, 4, 0.25),
]


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    server._BUILD_HEATMAP_CACHE.clear()
    monkeypatch.setattr(cvmod, "CVSERVER_API_KEY", "")
    yield
    server._BUILD_HEATMAP_CACHE.clear()


def _build(contracts=FIXTURE_CONTRACTS, ticker=TICKER):
    payload = {"ticker": ticker, "spot": 100.0, "expiries": [EXP],
               "contracts": [dict(c) for c in contracts], "data_source": "public_api"}

    async def fake_fetch(_ticker, max_expiries=4):
        return {**payload, "contracts": [dict(c) for c in payload["contracts"]]}

    async def _no_velocity(_ticker, _nodes):
        return {"velocity_score": 0, "rolling_floor": "stable",
                "rolling_ceiling": "stable", "history": []}

    with patch.object(server, "fetch_spot_and_chains_merged", new=fake_fetch), \
            patch.object(server, "save_snapshot", new=AsyncMock(return_value=None)), \
            patch.object(server, "velocity_and_rolling", new=_no_velocity):
        return _LOOP.run_until_complete(
            server._build_heatmap_impl(ticker, max_expiries=4, with_taps=False))


def _cell(section, strike_key):
    return ((section or {}).get("grid") or {}).get(EXP, {}).get(strike_key)


# ── R11-01 through the real builder ─────────────────────────────────────


def test_r11_01_four_surfaces_reproduce_independent_fixture():
    out = _build()
    grids = out["metrics"]["grids"]
    assert math.isclose(_cell(out["grid"], "100"), 100_000.0, rel_tol=1e-9)
    assert math.isclose(_cell(grids["delta"], "100"), 50_000.0, rel_tol=1e-9)
    assert math.isclose(_cell(grids["activity"], "100"), 10_000.0, rel_tol=1e-9)
    assert math.isclose(_cell(grids["session_delta_volume"], "100"), 5_000.0, rel_tol=1e-9)
    # The legacy activity key is NOT the delta-weighted one.
    assert grids["activity"]["exposure_basis"] == "VOLUME"
    assert grids["session_delta_volume"]["exposure_basis"] == "VOLUME_DELTA_WEIGHTED"


def test_r11_01_surfaces_share_ticker_formula_and_expiry_universe():
    out = _build()
    used = set(out["expiries_used"])
    for key in ("delta", "activity", "session_delta_volume"):
        sec = out["metrics"]["grids"][key]
        assert sec["formula_version"] == "gex.v2"
        assert set(sec["expiries"]) <= used, key
    assert out["metrics"]["formula_version"] == "gex.v2"
    assert out["ticker"] == TICKER


def test_missing_delta_is_unknown_not_zero_on_both_delta_surfaces():
    out = _build()
    grids = out["metrics"]["grids"]
    # Raw sees the put; the delta surfaces must not invent a value for it.
    assert math.isclose(_cell(out["grid"], "105"), -100_000.0, rel_tol=1e-9)
    assert _cell(grids["delta"], "105") is None
    assert _cell(grids["session_delta_volume"], "105") is None
    # ...and the cell is marked known-missing, so "no contracts" and
    # "contracts with unknown delta" are distinguishable per cell.
    assert grids["delta"]["cell_missing_delta"][EXP]["105"] == 1
    assert grids["session_delta_volume"]["cell_missing_delta"][EXP]["105"] == 1
    assert "100" not in grids["delta"]["cell_missing_delta"].get(EXP, {})


def test_per_surface_usable_missing_invalid_counts_are_reported():
    out = _build()
    cov = out["metrics"]["surface_coverage"]
    assert set(cov) >= {"raw", "delta", "activity", "session_delta_volume", "window"}
    assert cov["delta"]["usable"] == 2 and cov["delta"]["missing_delta"] == 1
    assert cov["session_delta_volume"]["usable"] == 2
    assert cov["session_delta_volume"]["missing_delta"] == 1
    assert cov["activity"]["usable"] == 3
    assert cov["raw"]["usable"] == 3
    for key in ("raw", "delta", "activity", "session_delta_volume"):
        assert cov[key]["metric_id"], key
        assert cov[key]["basis"], key
        assert cov[key]["status"] in ("ok", "partial", "unavailable"), key
    # One missing delta on a 3-contract population is PARTIAL, not "ok".
    assert cov["delta"]["status"] == "partial"
    assert cov["raw"]["status"] == "ok"
    # No recorded baseline in an in-memory store: window is unavailable
    # with a reason, never zero.
    assert cov["window"]["status"] == "unavailable" and cov["window"]["reason"]


def test_grid_level_usable_counts_match_domain_population():
    out = _build()
    grids = out["metrics"]["grids"]
    assert grids["delta"]["usable"] == out["metrics"]["dadgex_usable"] == 2
    assert grids["session_delta_volume"]["usable"] == out["metrics"]["session_delta_volume_usable"] == 2
    assert grids["activity"]["usable"] == out["metrics"]["volume_gamma_usable"] == 3


def test_window_reason_alias_carries_the_same_state():
    out = _build()
    m = out["metrics"]
    assert m["window_dadgex_v1"] is None and m["window_daddex_v1"] is None
    assert m["window_dadgex_reason"]
    assert m["window_daddex_reason"] == m["window_dadgex_reason"]
    # A refused window publishes an unavailable grid section, never raw.
    win = m["grids"]["window"]
    assert win["status"] == "unavailable" and win["reason"] == m["window_dadgex_reason"]
    assert not win.get("grid")


def test_wall_metrics_carry_session_delta_volume_with_its_own_basis():
    out = _build()
    wm = out["metrics"]["wall_metrics"]
    walls = out["metrics"]["walls"]
    hit = [w for w in walls if 100.0 in [float(x) for x in w.get("members", [])]]
    assert hit, "fixture must produce a wall containing strike 100"
    row = wm[hit[0]["wall_id"]]
    assert row["bases"] == {"daddex": "OI_DELTA_WEIGHTED", "volume": "VOLUME",
                            "session_delta_volume": "VOLUME_DELTA_WEIGHTED"}
    members = {float(x) for x in hit[0]["members"]}
    expected = sum(1000.0 * c["volume"] * abs(c["delta"]) * (1 if c["type"] == "call" else -1)
                   for c in FIXTURE_CONTRACTS
                   if c["strike"] in members and c["delta"] is not None)
    assert math.isclose(row["sdv_net"], expected, rel_tol=1e-9)
    n_missing = sum(1 for c in FIXTURE_CONTRACTS if c["strike"] in members and c["delta"] is None)
    assert row["sdv_missing_delta"] == n_missing
    # Legacy key kept for backward compatibility.
    assert row["basis"] == "OI_DELTA_WEIGHTED"


def test_same_population_raw_and_delta_reconcile_gross_and_net():
    """Raw and Δ-weighted gross/net over the SAME valid population.

    Delta net may exceed raw net in magnitude when weighting changes
    cancellation — no inequality is forced; the identity checked is the
    per-contract one: Δ contribution = raw contribution · |δ|.
    """
    out = _build()
    grids = out["metrics"]["grids"]
    for strike_key, delta in (("100", 0.5), ("95", 0.25)):
        raw_v = _cell(out["grid"], strike_key)
        d_v = _cell(grids["delta"], strike_key)
        assert math.isclose(d_v, raw_v * delta, rel_tol=1e-9)


def test_delta_net_can_exceed_raw_net_when_cancellation_changes():
    # call@100 δ .9 OI 100 vs put@100 δ -.1 OI 100: raw nets to 0, Δ does not.
    contracts = [_c(100, "call", 100, 10, 0.9), _c(100, "put", 100, 10, -0.1)]
    out = _build(contracts, ticker="R11CX")
    raw_v = _cell(out["grid"], "100")
    d_v = _cell(out["metrics"]["grids"]["delta"], "100")
    assert math.isclose(raw_v, 0.0, abs_tol=1e-6)
    assert abs(d_v) > abs(raw_v)


def test_fractional_strike_keeps_its_own_cell():
    contracts = [_c(100.5, "call", 100, 10, 0.5), _c(100, "call", 100, 10, 0.5)]
    out = _build(contracts, ticker="R11FS")
    sdv = out["metrics"]["grids"]["session_delta_volume"]
    assert math.isclose(_cell(sdv, "100.5"), 5_000.0, rel_tol=1e-9)
    assert math.isclose(_cell(sdv, "100"), 5_000.0, rel_tol=1e-9)


# ── window kernel: typed inputs (live window path) ──────────────────────


def _wc(delta=0.5, gamma=0.1, typ="call", vol0=10.0, vol1=30.0, **extra):
    base = {"osi": "X", "expiry": EXP, "strike": 100.0, "type": typ, "gamma": gamma,
            "delta": delta, **extra}
    return [{**base, "volume": vol0}], [{**base, "volume": vol1}]


def test_window_kernel_happy_path_value():
    prev, cur = _wc()
    out = window_contract_activity(prev, cur, 100.0)
    assert out["status"] == "ok"
    assert math.isclose(out["contracts"][0]["window_daddex"], 1000.0 * 0.5 * 20.0)


@pytest.mark.parametrize("field,value", [
    ("delta", True), ("delta", float("nan")), ("delta", float("inf")), ("delta", 1.2),
    ("gamma", True), ("gamma", float("nan")),
])
def test_window_kernel_rejects_typed_and_nonfinite_greeks_with_a_count(field, value):
    kw = {field: value}
    prev, cur = _wc(**kw)
    out = window_contract_activity(prev, cur, 100.0)
    assert out["contracts"] == [], f"{field}={value!r} must not produce a window row"
    excluded = out.get("missing_delta", 0) + out.get("invalid", 0)
    assert excluded == 1, f"{field}={value!r} must be counted, not silently dropped"


def test_window_kernel_rejects_unknown_option_type_instead_of_defaulting_to_put():
    prev, cur = _wc(typ="weird")
    out = window_contract_activity(prev, cur, 100.0)
    assert out["contracts"] == []
    assert out["invalid_type"] == 1


@pytest.mark.parametrize("mult", [0, -100, None, float("nan"), True])
def test_window_kernel_never_defaults_an_explicit_bad_multiplier_to_100(mult):
    prev, cur = _wc(multiplier=mult)
    out = window_contract_activity(prev, cur, 100.0)
    assert out["contracts"] == [], f"multiplier={mult!r} must be excluded"
    assert out["invalid"] == 1


def test_window_kernel_tiny_delta_overshoot_follows_registered_tolerance():
    prev, cur = _wc(delta=1.0 + 1e-12)
    out = window_contract_activity(prev, cur, 100.0)
    assert out["status"] == "ok" and len(out["contracts"]) == 1
    assert math.isclose(out["contracts"][0]["window_daddex"], 1000.0 * 1.0 * 20.0)


def test_window_kernel_boolean_volume_is_not_a_count():
    prev, cur = _wc(vol0=True, vol1=30.0)
    out = window_contract_activity(prev, cur, 100.0)
    assert out["contracts"] == []

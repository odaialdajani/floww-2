"""
Smoke tests for the consolidated steal-three router.

Verifies:
  * the router mounts cleanly into a FastAPI app
  * the expected paths are registered with the right HTTP methods
  * routes/steal_three.py is exported via routes/__init__.py so the main
    backend can include_router() it via server.py
  * the sidecar (:8001) mounts the same router without letting ``/health``
    collide with anything

These tests don't touch yfinance — they're pure API-surface smoke checks,
so they run sub-second with no network.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_minimal_app():
    """Stand up a FastAPI app that mirrors what backend/server.py does for
    this router — no Mongo / no Mongo client; the router itself is pure-
    yfinance, no shared services are imported by the tests."""
    from routes.steal_three import router as steal_three_router
    app = FastAPI(title="steal-three smoke")
    app.include_router(steal_three_router)
    return app


def _schema_paths(app: FastAPI) -> dict[str, dict]:
    """Return the public route contract, independent of router internals.

    FastAPI 0.141 stores included routers as nested route objects instead of
    flattening every child into ``app.routes``.  OpenAPI remains the supported
    public inventory and therefore works across both layouts.
    """
    return app.openapi()["paths"]


def test_router_exports_expected_paths():
    app = _build_minimal_app()
    paths = _schema_paths(app)
    # Three core endpoints must be present.
    assert "/api/dual_gex/{ticker}" in paths
    assert "/api/iv_mid/{ticker}" in paths
    assert "/api/screener/income" in paths


def test_router_exposes_get_methods_on_all_three_endpoints():
    app = _build_minimal_app()
    paths = _schema_paths(app)
    assert "get" in paths["/api/dual_gex/{ticker}"]
    assert "get" in paths["/api/iv_mid/{ticker}"]
    assert "get" in paths["/api/screener/income"]


def test_routes_init_exposes_steal_three_router():
    """server.py imports `steal_three_router` via `from routes import …`,
    so routes/__init__.py MUST re-export it — verify that binding exists."""
    from routes import steal_three_router  # noqa: F401
    assert steal_three_router is not None
    # And it's an APIRouter instance imported from the right submodule.
    from fastapi import APIRouter
    assert isinstance(steal_three_router, APIRouter)
    paths = sorted({r.path for r in steal_three_router.routes if hasattr(r, "path")})
    assert "/api/dual_gex/{ticker}" in paths


def test_sidecar_can_mount_router_without_collisions():
    """The :8001 sidecar builds its own FastAPI app — verify it can mount
    the same router and the only extra route is the sidecar's /health."""
    from services.steal_three_server import app as sidecar_app

    paths = _schema_paths(sidecar_app)
    # The 3 core endpoints are there.
    assert "/api/dual_gex/{ticker}" in paths
    assert "/api/iv_mid/{ticker}" in paths
    assert "/api/screener/income" in paths
    # Plus the sidecar-specific /health, and no collisions.
    assert "/health" in paths
    canonical_paths = _schema_paths(_build_minimal_app())
    assert set(paths) == set(canonical_paths) | {"/health"}


def test_router_minimal_request_validation():
    """Verify the screener rejects an obviously bad payload (max_dte < min_dte)."""
    client = TestClient(_build_minimal_app())
    r = client.get("/api/screener/income", params={"symbol": "SPY", "min_dte": 30, "max_dte": 7})
    assert r.status_code == 400
    body = r.json()
    assert "max_dte" in str(body.get("detail", body))


def test_router_minimal_request_validation_pattern():
    """The side= parameter has a regex pattern — confirm out-of-pattern values get 422."""
    client = TestClient(_build_minimal_app())
    r = client.get("/api/screener/income", params={"symbol": "SPY", "side": "sideways"})
    assert r.status_code in (400, 422)


def test_server_py_include_has_no_prefix():
    """Regression guard for the prefix-doubling ship-blocker.

    routes/steal_three.py registers paths starting with ``/api/...``. If the
    canonical include in backend/server.py sets ``prefix="/api"`` again, the
    final URLs become ``/api/api/dual_gex/...`` — a silent breaking change
    for every frontend caller. Lock the invariant in CI by reading server.py
    and confirming the include call has no ``prefix`` keyword.

    Robust against multi-line include wraps: the regex collapses all line
    breaks inside a single ``app.include_router(...)`` call before matching.
    """
    import pathlib
    import re
    server_py = pathlib.Path(__file__).resolve().parents[2] / "server.py"
    joined = " ".join(line.strip() for line in server_py.read_text().splitlines())
    m = re.search(r"app\.include_router\(\s*steal_three_router[^)]*\)", joined)
    assert m is not None, (
        "Could not find app.include_router(steal_three_router...) in server.py"
    )
    line = m.group(0)
    assert "prefix" not in line, (
        f"prefix must NOT be set on include_router(steal_three_router) — "
        f"routes already start with /api/, doubling would break all callers. "
        f"Found: {line!r}"
    )

# ---------------------------------------------------------------------------
# Integration smoke for the new /api/chain_consensus/{ticker} route.
# Locks (a) the FastAPI route registration + the through-line from
# _load_multi_expiry_chain to compute_consensus_per_expiry, and (b) the
# premium-resolver fallback chain (mid > lastPrice > 0) so a future
# yfinance schema drift that drops bid/ask silently flips the resolver
# to last-price — this test catches that.
#
# Patch strategy: monkey-patch routes.steal_three._load_multi_expiry_chain
# directly. Avoids constructing brittle pandas-DataFrame-like stubs of
# yf.Ticker; surgically replaces only the route's network boundary.
# ---------------------------------------------------------------------------
def test_chain_consensus_route_integration(monkeypatch):
    # Expiry 1 (all-call asymmetry + 3 distinct resolver paths in one fixture):
    #   Call 1: bid+ask present → premium=(1.9+2.1)/2=2.0, lastPrice=99 IGNORED
    #           (locks the "mid wins over lastPrice" decision)
    #   Call 2: bid/ask absent → premium=lastPrice=1.0
    #           (locks the "fall back to lastPrice" path)
    #   Call 3: bid/ask/lastPrice all absent → premium=0
    #           (locks the "fall back to 0" path)
    # Expiry 2 (all-put asymmetry): bid+ask → premium=(1.5+2.5)/2=2.0
    contracts = [
        # C1: bid+ask present → premium=(1.9+2.1)/2=2.0  (mid WINS over junk lastPrice=99)
        {"expiry": "2026-08-15", "type": "CALL", "strike": 100, "openInterest": 1000,
         "bid": 1.9, "ask": 2.1, "lastPrice": 99.0},
        # C2: bid/ask absent → premium falls back to lastPrice=1.0
        {"expiry": "2026-08-15", "type": "CALL", "strike": 105, "openInterest": 500,
         "lastPrice": 1.0},
        # C3: bid/ask AND lastPrice all absent → premium falls back to 0
        {"expiry": "2026-08-15", "type": "CALL", "strike": 110, "openInterest": 500},
        # P1 (all-put asymmetry): bid+ask → premium=(1.5+2.5)/2=2.0
        {"expiry": "2026-09-19", "type": "PUT",  "strike":  90, "openInterest": 1000,
         "bid": 1.5, "ask": 2.5},
    ]
    monkeypatch.setattr(
        'routes.steal_three._load_multi_expiry_chain',
        lambda ticker, expiries: (100.0, contracts, 2),
    )

    client = TestClient(_build_minimal_app())
    resp = client.get('/api/chain_consensus/SPY?expiries=2')
    assert resp.status_code == 200
    data = resp.json()
    assert data['ticker'] == 'SPY'
    assert data['spot'] == 100.0
    assert data['expiries_scanned'] == 2
    assert len(data['rows']) == 2

    # HAND-VERIFIED Expiry 1:
    #   weighted = 102000 + 53000 + 55000 = 210000  → consensus = 210000/2000 = 105.0
    #   avg_call_premium = (2.0*1000 + 1.0*500 + 0*500) / 2000 = 2500/2000 = 1.25
    r = data['rows'][0]
    assert r['expiry'] == '2026-08-15'
    assert r['consensus_price'] == 105.0
    assert r['total_oi'] == 2000
    assert r['call_oi'] == 2000
    assert r['put_oi'] == 0
    assert r['avg_call_premium'] == 1.25
    assert r['avg_put_premium'] == 0.0

    # HAND-VERIFIED Expiry 2:
    #   weighted = 88*1000 = 88000  → consensus = 88.0
    r2 = data['rows'][1]
    assert r2['expiry'] == '2026-09-19'
    assert r2['consensus_price'] == 88.0
    assert r2['total_oi'] == 1000
    assert r2['call_oi'] == 0
    assert r2['put_oi'] == 1000
    assert r2['avg_call_premium'] == 0.0
    assert r2['avg_put_premium'] == 2.0

    # HAND-VERIFIED overall blend:
    #   weighted = 210000 + 88000 = 298000
    #   total_oi = 3000  → consensus = 298000/3000 = 99.3333…
    assert data['overall']['consensus_price'] == 99.3333
    assert data['overall']['total_oi'] == 3000
    assert data['overall']['call_oi'] == 2000
    assert data['overall']['put_oi'] == 1000


# ---------------------------------------------------------------------------
# Regression — /api/dual_gex must survive BARE yfinance rows.
#
# yfinance option_chain() DataFrames carry no type/option_type/opt_type
# column — the side lives only in the calls-vs-puts split that
# _load_chain() returns. The route must stamp the side onto each contract
# before handing them to DualGexCalculator, whose _resolve raises KeyError
# otherwise (surfaced live as HTTP 500 on /api/dual_gex/SPY, 2026-07-15).
#
# Patch strategy mirrors test_chain_consensus_route_integration: replace
# only the network boundary (routes.steal_three._load_chain).
# ---------------------------------------------------------------------------
def test_dual_gex_route_survives_bare_yfinance_rows(monkeypatch):
    calls = [{"strike": 100.0, "openInterest": 10, "volume": 5.0,
              "bid": 1.0, "ask": 1.2, "expiry": "2026-08-15"}]
    puts = [{"strike": 90.0, "openInterest": 20, "volume": 2.0,
             "bid": 0.8, "ask": 1.0, "expiry": "2026-08-15"}]
    monkeypatch.setattr(
        "routes.steal_three._load_chain",
        lambda ticker, expiry_index=0: (100.0, calls, puts, "2026-08-15"),
    )

    client = TestClient(_build_minimal_app())
    resp = client.get("/api/dual_gex/SPY")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ticker"] == "SPY"
    assert data["spot"] == 100.0
    # Both sides must have been accepted (one call strike, one put strike).
    assert sorted(data["strikes"]) == [90.0, 100.0]
    assert data["activity_badge"] in ("quiet", "active", "live")


# ---------------------------------------------------------------------------
# Regression — /api/screener/income must scan expiries INSIDE the DTE window.
#
# The route originally loaded only the FRONT expiry (_load_chain →
# expiry_index=0 → today's 0DTE) and then filtered min_dte>=7, so it
# structurally always returned empty puts/calls (live empty-response,
# 2026-07-15). Fix: a side-preserving windowed loader + pure expiry picker.
# ---------------------------------------------------------------------------
def test_select_expiries_in_window_pure():
    from datetime import date

    from routes.steal_three import _select_expiries_in_window

    today = date(2026, 7, 15)
    listed = ["2026-07-15", "2026-07-16", "2026-07-24",   # dte 0, 1, 9
              "2026-08-21", "2026-10-16", "garbage"]      # dte 37, 93, skip
    assert _select_expiries_in_window(listed, 7, 45, today=today) == [
        "2026-07-24", "2026-08-21",
    ]
    # cap honored
    assert _select_expiries_in_window(listed, 0, 365, cap=2, today=today) == [
        "2026-07-15", "2026-07-16",
    ]
    # nothing in window
    assert _select_expiries_in_window(listed, 200, 300, today=today) == []


def test_screener_income_returns_rows_from_windowed_chain(monkeypatch):
    # Future expiry — hard-coded dates expired and the min_dte filter
    # started dropping every row (time-bomb test, fixed 2026-08-23).
    from datetime import date, timedelta
    future_exp = (date.today() + timedelta(days=21)).isoformat()
    put_row = {"strike": 95.0, "expiry": future_exp, "openInterest": 500,
               "volume": 40, "bid": 1.0, "ask": 1.2, "impliedVolatility": 0.25}
    call_row = {"strike": 105.0, "expiry": future_exp, "openInterest": 300,
                "volume": 30, "bid": 0.9, "ask": 1.1, "impliedVolatility": 0.22}
    monkeypatch.setattr(
        "routes.steal_three._load_chain_window",
        lambda symbol, min_dte, max_dte, cap=8: (100.0, [call_row], [put_row]),
    )

    client = TestClient(_build_minimal_app())
    resp = client.get("/api/screener/income?symbol=SPY&side=both&min_dte=7&max_dte=45")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["symbol"] == "SPY"
    # The windowed rows must flow through to the ranked output.
    assert len(data["puts"]) == 1
    assert len(data["calls"]) == 1
    assert data["puts"][0]["strike"] == 95.0


# ---------------------------------------------------------------------------
# Regression — /api/iv_mid must not solve on the 0DTE front expiry.
#
# _load_chain defaults to expiry_index=0 (often TODAY → dte=0 → T=0.0), and
# a T=0 Black-Scholes solve is impossible: live behavior was every row
# solved_iv_is_invalid=true all day (2026-07-15). iv_mid must request the
# first expiry with dte >= 1.
# ---------------------------------------------------------------------------
def test_iv_mid_requests_min_dte_1(monkeypatch):
    captured = {}

    def fake_load(ticker, expiry_index=0, min_dte=0):
        captured["min_dte"] = min_dte
        return (100.0, [], [], "2026-08-21")

    monkeypatch.setattr("routes.steal_three._load_chain", fake_load)
    client = TestClient(_build_minimal_app())
    resp = client.get("/api/iv_mid/SPY")
    assert resp.status_code == 200, resp.text
    assert captured["min_dte"] == 1


def test_iv_row_returns_json_native_types():
    """Regression: implied_vol_from_price returns np.float64 when the Newton
    solve actually runs (T>0), so `solved_iv == 0.0` produced a numpy.bool —
    PydanticSerializationError 500 on /api/iv_mid (2026-07-15). _iv_row must
    emit JSON-native types only."""
    from routes.steal_three import _iv_row

    row = {"strike": 100.0, "bid": 4.8, "ask": 5.2,
           "lastPrice": 5.0, "impliedVolatility": 0.22}
    r = _iv_row(row, 100.0, 30 / 365, "call")
    assert type(r["solved_iv_is_invalid"]) is bool
    assert not hasattr(r["solved_iv"], "dtype")
    assert not hasattr(r["round_trip_diff"], "dtype")


# --------------------------------------------------------------------------
# Steal-list triage (2026-07-15): 5 regression tests pinning the contract
# for the 4 endpoints the user reported as failing.
#   * /api/dual_gex              — 500 → defensive-degrade wrap (test #1).
#   * /api/wheel_income/        — 404 → backwards-compat alias (test #2).
#   * /api/regime_persistence    — 404 → missing route, shipped now
#                                  (tests #3 + #4).
#   * /api/chain_consensus      — perceived partial-body → contract pin
#                                  (test #5).
# Each test guards a specific failure mode so future route-layer refactors
# can't silently regress to the 2026-07-15 broken state.
# --------------------------------------------------------------------------
def test_dual_gex_route_defensive_degrade_when_calculator_raises(monkeypatch):
    """If DualGexCalculator.compute() raises (truly malformed broker row,
    regression in GexAggregator._resolve, etc.), the route MUST swallow
    the exception and return the empty-shape dict — never a 500 that
    would crash the Heatseeker dashboard. The empty shape mirrors
    DualGexCalculator.empty + the route's documented decorations so
    DualGEXBadge.jsx renders the offline tile cleanly.
    """
    from services.gex_dual import DualGexCalculator

    # Setup _load_chain to return a valid tuple so the route enters
    # the try block (vs. failing at _load_chain with a real 404).
    calls = [{"strike": 100.0, "openInterest": 10, "volume": 5.0,
              "bid": 1.0, "ask": 1.2, "expiry": "2026-08-15"}]
    puts = [{"strike": 90.0, "openInterest": 20, "volume": 2.0,
             "bid": 0.8, "ask": 1.0, "expiry": "2026-08-15"}]
    monkeypatch.setattr(
        "routes.steal_three._load_chain",
        lambda ticker, expiry_index=0: (100.0, calls, puts, "2026-08-15"),
    )

    # Force the calculator to raise — this is the fault the wrap guards.
    def _boom(_spot, _contracts):
        raise RuntimeError("simulated broker-shape regression")
    monkeypatch.setattr(DualGexCalculator, "compute", staticmethod(_boom))

    client = TestClient(_build_minimal_app())
    resp = client.get("/api/dual_gex/SPY")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Empty-shape contract: every documented key present with the
    # zero/empty default so DualGEXBadge.jsx never sees a key error.
    assert data["ticker"] == "SPY"
    assert data["spot"] == 0.0
    assert data["strikes"] == []
    assert data["gex_oi_1d"] == []
    assert data["gex_volume_1d"] == []
    assert data["total_gex"] == 0.0
    assert data["net_gex_oi"] == 0.0
    assert data["net_gex_volume"] == 0.0
    assert data["gex_oi_total"] == 0.0
    assert data["gex_volume_total"] == 0.0
    assert data["activity_ratio"] == 0.0
    assert data["activity_badge"] == "quiet"
    assert data["positive_gex_oi"] == 0.0
    assert data["positive_gex_volume"] == 0.0
    # error key set — the badge will display the cause for triage.
    assert data["error"] is not None
    assert "RuntimeError" in data["error"]
    assert "simulated broker-shape regression" in data["error"]


def test_wheel_income_alias_calls_same_screener_logic(monkeypatch):
    """``/api/wheel_income/{ticker}`` is the backwards-compat alias
    added by the 2026-07-15 triage. It MUST produce IDENTICAL output
    to the canonical ``/api/screener/income?symbol=...`` route so
    callers that use either URL get the same ranked candidates — the
    alias is a pure URI-rewrite, not a divergent code path.
    """
    # Future expiry — hard-coded dates expired and the min_dte filter
    # started dropping every row (time-bomb test, fixed 2026-08-23).
    from datetime import date, timedelta
    future_exp = (date.today() + timedelta(days=21)).isoformat()
    put_row = {"strike": 95.0, "expiry": future_exp, "openInterest": 500,
               "volume": 40, "bid": 1.0, "ask": 1.2, "impliedVolatility": 0.25}
    call_row = {"strike": 105.0, "expiry": future_exp, "openInterest": 300,
                "volume": 30, "bid": 0.9, "ask": 1.1, "impliedVolatility": 0.22}
    monkeypatch.setattr(
        "routes.steal_three._load_chain_window",
        lambda symbol, min_dte, max_dte, cap=8: (100.0, [call_row], [put_row]),
    )

    client = TestClient(_build_minimal_app())
    canonical = client.get(
        "/api/screener/income?symbol=SPY&side=both&min_dte=7&max_dte=45"
    ).json()
    aliased = client.get(
        "/api/wheel_income/SPY?side=both&min_dte=7&max_dte=45"
    ).json()

    # The two routes share the ``_run_income_screener`` helper so the
    # contracts agree on every ranked row + filter/echo metadata.
    assert canonical["symbol"] == aliased["symbol"] == "SPY"
    assert canonical["spot"] == aliased["spot"]
    assert canonical["filters"] == aliased["filters"]
    assert canonical["puts"] == aliased["puts"]
    assert canonical["calls"] == aliased["calls"]
    assert canonical["source"] == aliased["source"]


def test_regime_persistence_route_present():
    """The 2026-07-15 triage confirmed ``/api/regime_persistence/{ticker}``
    was 404 because the route WAS NOT MOUNTED. This smoke test pins the
    @router.get path is now present on the FastAPI app — future
    refactors that delete the line by mistake will fail this test
    directly.
    """
    app = _build_minimal_app()
    paths = _schema_paths(app)
    assert "/api/regime_persistence/{ticker}" in paths
    # And the method is GET.
    assert "get" in paths["/api/regime_persistence/{ticker}"]


def test_regime_persistence_route_handles_mongo_unreachable(monkeypatch):
    """If MongoDB access fails (MongoDown, scheduler paused, ticker has
    no chain data, etc.) the route MUST return the canonical
    empty-metrics response — never a 500. The defensive-degrade
    contract matches consensus_drift + max_pain_drift pattern.
    """
    # Patch the helper the route reaches for AFTER it imports db, so
    # the route still completes `from server import db as mongo_db`
    # before the helper's raise short-circuits the chain.
    def _mongo_down(_ticker, **_kwargs):
        raise RuntimeError("simulated MongoDB unreachable")
    monkeypatch.setattr(
        "services.gex_history.get_gex_history_sync", _mongo_down,
    )

    client = TestClient(_build_minimal_app())
    resp = client.get("/api/regime_persistence/SPY?days=30")
    # The DB raise is caught — route returns a structured empty body,
    # NOT a 500.
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Documented empty-metrics contract pinned here so a future
    # refactor can't quietly change the shape.
    assert data["ticker"] == "SPY"
    assert data["regime"] is None
    assert data["sign_persistence_pct"] == 0.0
    assert data["flip_count"] == 0
    assert data["magnitude_conviction"] == 0.0
    assert data["coefficient_of_variation"] == 0.0
    assert data["n_days_covered"] == 0
    assert data["window_label"] == "30d"
    assert any("RuntimeError" in w for w in data["warnings"])
    assert any("simulated MongoDB unreachable" in w for w in data["warnings"])


def test_chain_consensus_endpoint_returns_documented_keys(monkeypatch):
    """The 2026-07-15 user-perceived "partial body" probably stems from
    the per-row ``rows[]`` listing the first 8 expiries only (most-
    liquid front-of-chain), NOT from a truncated schema. This test
    pins the EXACT schema contract — top-level keys, per-row keys,
    overall keys — so a future "regional completeness" decision can't
    silently truncate the response shape.
    """
    contracts = [
        {"expiry": "2026-08-15", "type": "CALL", "strike": 100,
         "openInterest": 1000, "bid": 1.9, "ask": 2.1, "lastPrice": 2.0},
        {"expiry": "2026-09-19", "type": "PUT",  "strike":  90,
         "openInterest": 1000, "bid": 1.5, "ask": 2.5, "lastPrice": 2.0},
    ]
    monkeypatch.setattr(
        "routes.steal_three._load_multi_expiry_chain",
        lambda ticker, expiries: (100.0, contracts, 2),
    )

    client = TestClient(_build_minimal_app())
    resp = client.get("/api/chain_consensus/SPY?expiries=2")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # Top-level keys contract.
    expected_top = {"ticker", "spot", "expiries_scanned", "rows", "overall", "source"}
    assert set(data.keys()) == expected_top, (
        f"top-level keys diverged: got {sorted(data.keys())} "
        f"expected {sorted(expected_top)}"
    )

    # Per-row keys contract.
    expected_row = {
        "expiry", "consensus_price", "total_oi",
        "call_oi", "put_oi", "avg_call_premium", "avg_put_premium",
    }
    assert all(set(r.keys()) == expected_row for r in data["rows"]), (
        f"row keys diverged: got {[set(r.keys()) for r in data['rows']]} "
        f"expected {expected_row}"
    )

    # Overall keys contract.
    # NOTE: ``expiry`` is included because compute_overall_consensus stamps
    # the OVERALL bucket's synthetic expiry label (a documented
    # convenience so downstream callers don't have to special-case the
    # absence of an expiry key). The per-row keys already include
    # ``expiry`` for the same reason — they're for individual listed
    # expiries.
    expected_overall = {
        "expiry", "consensus_price", "total_oi", "call_oi", "put_oi",
        "avg_call_premium", "avg_put_premium",
    }
    assert set(data["overall"].keys()) == expected_overall, (
        f"overall keys diverged: got {sorted(data['overall'].keys())} "
        f"expected {sorted(expected_overall)}"
    )

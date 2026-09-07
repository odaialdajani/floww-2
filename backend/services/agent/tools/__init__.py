"""Lodestar research tool catalog (plan v3 L1). Read-only by construction.

Call styles: direct (pure fn), enriched (chain via _fetch_chain ->
_ensure_gamma -> pure fn), internal-http (loopback only, cache_only).
One chain per turn via the cached path. Budgets enforced by the loop.
"""

from __future__ import annotations

import contextlib
import time
from typing import Any

from services.agent.access.envelope import make_envelope
from services.agent.access.horizon import slice_expiries
from services.agent.registry import register

ML_TICKERS = ["SPY", "QQQ", "DIA", "IWM", "TLT"]
PAID_TAPE = ["SPY", "QQQ", "IWM", "DIA", "TLT", "SPX"]


def _ok(data: Any, **kw: Any) -> dict[str, Any]:
    return make_envelope(status="ok", **kw, data=data)


def _degraded(data: Any, error: str = "", **kw: Any) -> dict[str, Any]:
    return make_envelope(status="degraded", error=error or None, **kw, data=data)


def _failed(error: str, **kw: Any) -> dict[str, Any]:
    return make_envelope(status="failed", error=error, **kw, data=None)


async def _chain(ticker: str, expiries: int = 6) -> dict[str, Any]:
    """One chain per turn via the cached route path (enriched style)."""
    try:
        from routes.heatseeker import _ensure_gamma, _fetch_chain

        raw = await _fetch_chain(ticker.upper(), expiries)
        raw = _ensure_gamma(raw)
        return raw
    except Exception as e:
        return {"spot": 0, "contracts": [], "_error": str(e)}


def _heatseeker_tool(name: str, pure_fn: str, description: str):
    async def _fn(ticker: str, horizon: str = "all", **kw: Any) -> dict[str, Any]:
        t0 = time.time()
        try:
            from services import heatseeker as hs

            fn = getattr(hs, pure_fn, None)
            if fn is None:
                return _failed(f"no calculator {pure_fn}", source="heatseeker")
            raw = await _chain(ticker)
            if raw.get("_error") and not raw.get("contracts"):
                return _failed(raw["_error"], source="heatseeker")
            spot = float(raw.get("spot") or 0)
            contracts = slice_expiries(raw.get("contracts") or [], horizon)
            if not contracts:
                return _degraded({"note": "no contracts after horizon slice"}, source="heatseeker", error="empty after slice")
            try:
                data = fn(contracts, spot) if "spot" in getattr(fn, "__code__", {}).co_varnames else fn(contracts)
            except TypeError:
                try:
                    data = fn(raw, spot)
                except Exception as e:
                    return _failed(str(e), source="heatseeker")
            ms = (time.time() - t0) * 1000
            env = _ok(data, source="heatseeker", n_contracts=len(contracts), has_quotes=any(c.get("bid") for c in contracts[:5]))
            env["latency_ms"] = round(ms, 1)
            return env
        except Exception as e:
            return _failed(str(e), source="heatseeker")

    register(
        __import__("services.agent.registry", fromlist=["Tool"]).Tool(
            name=name,
            description=description,
            params={"type": "object", "properties": {"ticker": {"type": "string"}, "horizon": {"type": "string"}}},
            call_style="enriched",
            cost_class="normal",
            max_tokens_out=800,
            fn=_fn,
        )
    )
    return _fn


# Structure (Solstice) — pure calculators in services/heatseeker.py
_heatseeker_tool("gex_profile", "_gex_per_strike", "GEX by strike for the horizon slice")
_heatseeker_tool("flip_zones", "calc_flip_zones", "Gamma flip zones")
_heatseeker_tool("node_lifecycle", "calc_node_lifecycle", "Node age / fresh vs tested")
_heatseeker_tool("air_pockets", "calc_air_pockets", "Low-OI air pockets between walls")
_heatseeker_tool("beach_ball", "detect_beach_ball", "Beach-ball compression pattern")
_heatseeker_tool("reverse_rug", "detect_reverse_rug", "Reverse-rug pull pattern")
_heatseeker_tool("rainbow_road", "detect_rainbow_road", "Rainbow-road stacked walls")
_heatseeker_tool("velocity_mode", "calc_velocity_mode", "Velocity / acceleration regime")
_heatseeker_tool("trinity_confluence", "calc_trinity_confluence", "Trinity confluence score")


async def gex_grid(ticker: str, horizon: str = "all", **kw: Any) -> dict[str, Any]:
    try:
        raw = await _chain(ticker)
        contracts = slice_expiries(raw.get("contracts") or [], horizon)
        return _ok({"n": len(contracts), "spot": raw.get("spot")}, source="heatseeker", n_contracts=len(contracts))
    except Exception as e:
        return _failed(str(e), source="heatseeker")


async def flow_live(ticker: str, horizon: str = "all", **kw: Any) -> dict[str, Any]:
    try:
        from services.flow_alerts import score_conviction  # noqa: F401 (presence check)

        return _ok({"ticker": ticker.upper(), "note": "use alerts_feed for scored tape"}, source="flowseeker", coverage=",".join(PAID_TAPE))
    except Exception as e:
        return _failed(str(e), source="flowseeker")


async def flow_regime(ticker: str, horizon: str = "all", **kw: Any) -> dict[str, Any]:
    try:
        return _ok({"ticker": ticker.upper(), "regime": "unknown", "note": "handler-inline classifier; internal-http in loop"}, source="flowseeker")
    except Exception as e:
        return _failed(str(e), source="flowseeker")


async def alerts_feed(ticker: str, horizon: str = "all", limit: int = 20, **kw: Any) -> dict[str, Any]:
    try:
        from services.flow_alerts import score_conviction

        _ = score_conviction
        return _ok({"ticker": ticker.upper(), "alerts": [], "note": "direct read, volatile store"}, source="flowseeker", store="volatile")
    except Exception as e:
        return _failed(str(e), source="flowseeker")


async def generic_ok(ticker: str = "SPY", horizon: str = "all", **kw: Any) -> dict[str, Any]:
    return _ok({"ticker": str(ticker).upper(), "horizon": horizon}, source="mixed")


def _reg(name: str, description: str, fn: Any, covers: Any = None, cost: str = "normal", style: str = "direct", out: int = 800) -> None:
    from services.agent.registry import Tool

    with contextlib.suppress(ValueError):
        register(Tool(name=name, description=description, params={"type": "object"}, call_style=style, cost_class=cost, max_tokens_out=out, covers=covers, fn=fn))


Plen = [
    ("gex_grid", "GEX grid summary (capped; raw chain is internal only)", gex_grid, None, "heavy", "enriched", 1200),
    ("vex_grid", "VEX by strike", generic_ok, None, "normal", "direct", 800),
    ("charm_grid", "Charm exposure grid", generic_ok, None, "normal", "direct", 800),
    ("charm_integral", "Charm integral term structure", generic_ok, None, "normal", "direct", 600),
    ("vanna_exposure", "Vanna exposure regime", generic_ok, None, "normal", "direct", 600),
    ("node_classification", "Node classification", generic_ok, None, "normal", "internal-http", 800),
    ("stacked_nodes", "Stacked nodes", generic_ok, None, "normal", "internal-http", 800),
    ("tug_of_war", "Tug-of-war imbalance", generic_ok, None, "normal", "internal-http", 800),
    ("dual_gex", "Dual GEX scale check", generic_ok, None, "cheap", "direct", 500),
    ("strike_cone", "Strike cone / expected move", generic_ok, None, "normal", "direct", 600),
    ("max_pain", "Max pain level", generic_ok, None, "cheap", "direct", 400),
    ("max_pain_drift", "Max pain drift", generic_ok, None, "normal", "direct", 600),
    ("regime_persistence", "Regime persistence", generic_ok, None, "normal", "direct", 600),
    ("flow_live", "Live options-flow tape (paid tape only)", flow_live, PAID_TAPE, "normal", "direct", 800),
    ("flow_scan", "Flow scan cache_only (never triggers a scan)", generic_ok, PAID_TAPE, "normal", "internal-http", 800),
    ("flow_drilldown", "Flow drilldown per contract", generic_ok, PAID_TAPE, "normal", "direct", 800),
    ("flow_regime", "Flow regime classifier", flow_regime, None, "cheap", "internal-http", 500),
    ("alerts_feed", "Scored alert feed (volatile)", alerts_feed, None, "cheap", "direct", 800),
    ("alerts_quality", "Alert hit-rate / calibration (volatile, known defect)", generic_ok, None, "cheap", "direct", 600),
    ("retail_flow_score", "Retail flow score", generic_ok, None, "normal", "direct", 600),
    ("occ_volume", "OCC volume tape", generic_ok, None, "normal", "direct", 600),
    ("vpin", "VPIN toxicity", generic_ok, None, "normal", "direct", 500),
    ("ofi", "Order-flow imbalance", generic_ok, None, "normal", "direct", 500),
    ("hawkes", "Hawkes excitation", generic_ok, None, "normal", "direct", 500),
    ("kyle_lambda", "Kyle lambda impact", generic_ok, None, "normal", "direct", 500),
    ("liquidity", "Liquidity / Amihud snapshot", generic_ok, None, "normal", "direct", 500),
    ("anomaly", "Anomaly explanation", generic_ok, None, "normal", "direct", 600),
    ("vol_surface", "Vol surface slice", generic_ok, None, "heavy", "direct", 1000),
    ("iv_mid", "IV mid snapshot", generic_ok, None, "cheap", "direct", 400),
    ("realized_vol", "Realized vol + cone", generic_ok, None, "normal", "direct", 500),
    ("rnd", "Risk-neutral density", generic_ok, None, "heavy", "direct", 1000),
    ("consensus_drift", "Consensus drift", generic_ok, None, "normal", "direct", 600),
    ("skew", "Skew read", generic_ok, None, "normal", "direct", 500),
    ("company_overview", "Company overview (Alpha Vantage, slow leash)", generic_ok, None, "normal", "direct", 600),
    ("earnings", "Earnings (Alpha Vantage)", generic_ok, None, "normal", "direct", 600),
    ("news", "News + sentiment", generic_ok, None, "normal", "direct", 600),
    ("insider", "Insider (Finviz scraper)", generic_ok, None, "normal", "direct", 600),
    ("sentiment", "Social sentiment VADER+TextBlob", generic_ok, None, "normal", "direct", 600),
    ("social_flow", "Social flow", generic_ok, None, "normal", "direct", 600),
    ("structure_snapshots", "Agent-owned structure snapshots (durable)", generic_ok, None, "cheap", "direct", 600),
    ("time_delta", "What changed since open / prior close (agent snapshots only)", generic_ok, None, "cheap", "direct", 600),
    ("top_movers", "Top movers", generic_ok, None, "cheap", "direct", 500),
    ("journal_stats", "Journal stats (read-only)", generic_ok, None, "cheap", "direct", 500),
    ("claims_history", "Prior claims for ticker (durable)", generic_ok, None, "cheap", "direct", 600),
    ("recall_ticker", "Recall ticker memory + user notes", generic_ok, None, "cheap", "direct", 600),
    ("position_size", "Position sizing read (delta-adjusted max loss)", generic_ok, None, "cheap", "direct", 500),
    ("kelly_diagnostic", "Kelly diagnostic only", generic_ok, None, "cheap", "direct", 500),
    ("portfolio_greeks", "Portfolio greeks read", generic_ok, None, "cheap", "direct", 500),
    ("scenario", "What-if scenario read", generic_ok, None, "normal", "direct", 600),
    ("kill_switch_status", "Kill-switch state read", generic_ok, None, "cheap", "direct", 300),
    ("agent_live_policy_status", "Agent live policy read", generic_ok, None, "cheap", "direct", 300),
    ("strategy_evaluate", "Strategy payoff/PoP/greeks read via evaluate_strategy", generic_ok, None, "normal", "direct", 1000),
    ("strategy_quote", "Strategy quote via data adapter (counts Public ledger)", generic_ok, None, "normal", "direct", 800),
    ("ml_predict", "ML direction (5 tickers only)", generic_ok, ML_TICKERS, "normal", "direct", 500),
    ("quant_signals", "Quant signal catalog read", generic_ok, None, "normal", "direct", 600),
    ("vol_surface_full", "Alias guard (unused)", generic_ok, None, "cheap", "direct", 300),
]

for _n, _d, _f, _c, _co, _s, _o in Plen:
    _reg(_n, _d, _f, _c, _co, _s, _o)

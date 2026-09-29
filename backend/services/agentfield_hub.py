"""
services/agentfield_hub.py

AgentField Integration Hub for floww Trading Terminal.

Wraps existing floww services (GEX, alerts, portfolio, morning briefing) as
AgentField "reasoners" — callable via REST, schedulable via cron triggers,
trackable via execution context, and observable via cost/process logs.

This module creates an AgentField Agent instance in dev_mode (no control plane
server needed) and registers all trading reasoners from existing services.

Usage:
    from services.agentfield_hub import init_hub
    hub = await init_hub()   # call once at server startup
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# ── AgentField SDK imports ────────────────────────────────────────────────
from agentfield import Agent, AgentRouter, AIConfig, CostTracker  # type: ignore

# ── Singleton ──────────────────────────────────────────────────────────────
_hub: AgentFieldHub | None = None


def get_hub() -> AgentFieldHub:
    global _hub
    if _hub is None:
        _hub = AgentFieldHub()
    return _hub


async def init_hub() -> AgentFieldHub:
    hub = get_hub()
    await hub.init()
    return hub


class AgentFieldHub:
    """
    Central AgentField integration point.

    In dev_mode the Agent runs standalone — no AgentField control plane server
    required. All reasoners are registered locally and served via the existing
    FastAPI app at /agentfield/v1/*.
    """

    def __init__(self) -> None:
        self.agent: Agent | None = None
        self.cost_tracker = CostTracker()
        self.router = AgentRouter(prefix="/agentfield/v1", tags=["trading"])
        self._initialized = False

    async def init(self) -> None:
        if self._initialized:
            return

        model = os.getenv("AGENTFIELD_MODEL", "anthropic/claude-sonnet-4-20250514")
        ai_config = AIConfig(model=model)

        self.agent = Agent(
            node_id="floww-trading",
            version="1.0.0",
            ai_config=ai_config,
            dev_mode=True,
        )

        self._register_signal_reasoners()
        self._register_risk_reasoners()
        self._register_briefing_reasoners()
        self._register_data_reasoners()
        self._register_execution_reasoners()

        self.agent.include_router(self.router)
        self._initialized = True
        logger.info("AgentField hub initialized (node_id=floww-trading, model=%s)", model)

    # ──────────────────────────────────────────────────────────────────────
    #  Signal Processing Reasoners
    # ──────────────────────────────────────────────────────────────────────
    @staticmethod
    async def _canonical_gex_profile(ticker: str) -> dict[str, Any] | None:
        """Spot / net GEX / flip level from the canonical Public chain + engine.

        DEAD-WIRE REPAIR. This reasoner used to open with

            from services.heatseeker import compute_gex_profile

        which does not exist — the name is undefined, so the reasoner raised
        on every call and the remaining body never ran. Nothing reported a
        failure because the reasoner's own `try` was BELOW the import.

        The profile is now built from the platform's canonical path: the
        Public chain adapter for contracts, `gex_core` for the vendor-gamma
        GEX rows, and `find_zero_crossings` for the flip level. The flip is
        the canonical root computation, not a sign-change guess between
        adjacent strikes.

        Returns None when coverage is genuinely missing — never a zero-filled
        profile, because a zeroed spot or flip reads as a real level.
        """
        from services.gex_core import compute_gex_by_strike_vendor, find_zero_crossings
        from services.public_api_adapter import fetch_chain_from_public_api

        chain = await fetch_chain_from_public_api(ticker.upper(), max_expiries=4)
        if not chain or not chain.get("contracts"):
            return None
        try:
            spot = float(chain.get("spot") or 0.0)
        except (TypeError, ValueError):
            return None
        if spot <= 0:
            return None
        rows = compute_gex_by_strike_vendor(spot, chain["contracts"])
        if not rows:
            return None
        net = sum(float(r.get("gex") or 0.0) for r in rows)
        roots = find_zero_crossings(spot, rows)
        return {
            "spot": spot,
            "net_gex": net,
            "flip_level": float(roots[0]) if roots else None,
            "gex_rows": len(rows),
            "expiries": chain.get("expiries") or [],
            "data_source": chain.get("data_source"),
        }

    def _register_signal_reasoners(self) -> None:
        @self.router.reasoner(path="/signals/gex-regime", tags=["signal", "gex"])
        async def gex_regime(ticker: str = "SPY") -> dict[str, Any]:
            """Compute GEX regime for a ticker. Returns paper-accurate metrics."""
            try:
                profile = await self._canonical_gex_profile(ticker)
            except Exception as exc:
                logger.error("gex_regime profile error: %s", exc)
                return {"ticker": ticker.upper(), "status": "error", "error": str(exc)}
            if profile is None:
                # Coverage is missing. This is reported, not zero-filled: a
                # zeroed spot or flip level reads as a real level downstream.
                return {
                    "ticker": ticker.upper(),
                    "status": "unavailable",
                    "reason": "NO_CHAIN_COVERAGE",
                }
            try:
                result: dict[str, Any] = {"ticker": ticker.upper(), "status": "ok", **profile}

                # ── Paper-accurate metrics (Barbon-Buraschi + Ni-Pearson) ──
                try:
                    from services.gex_paper_accurate import (  # noqa: F811
                        compute_flip_metrics,
                        compute_gamma_imbalance,
                        flash_crash_risk,
                        gamma_liquidity_regime,
                        predict_intraday_regime,
                        vix_gamma_fragility,
                    )

                    spot = result.get("spot") or 0
                    net_gex = result.get("net_gex") or 0
                    # Unknown, never defaulted to a number. `result.get("vix", 22)`
                    # used to invent a 22 vol reading for every ticker, and the
                    # fragility metric below consumed it as if measured.
                    vix = result.get("vix")
                    flip_level = result.get("flip_level")

                    gib = compute_gamma_imbalance(net_gex, spot)
                    flip = compute_flip_metrics(flip_level, spot)
                    regime = predict_intraday_regime(gib.get("gamma_imbalance_pct", 0))
                    crash = flash_crash_risk(gib.get("gamma_imbalance_pct", 0))
                    liq = gamma_liquidity_regime(gib.get("gamma_imbalance_pct", 0), flip.get("flip_distance_pct", 100))

                    result["paper_metrics"] = {
                        "gamma_imbalance": gib,
                        "flip_metrics": flip,
                        "intraday_regime": regime,
                        "flash_crash_risk": crash,
                        "gamma_liquidity_regime": liq,
                        "net_gex_dollars": net_gex,
                    }
                    # Only computed when a real vol reading exists.
                    if isinstance(vix, (int, float)) and not isinstance(vix, bool):
                        result["paper_metrics"]["vix_gamma_fragility"] = vix_gamma_fragility(
                            vix_spot=vix,
                            gamma_imbalance_pct=gib.get("gamma_imbalance_pct", 0),
                            flip_distance_pct=flip.get("flip_distance_pct", 100),
                        )
                    else:
                        result["paper_metrics"]["vix_gamma_fragility"] = None
                        result["paper_metrics"]["vix_unavailable_reason"] = "VIX_NOT_PROVIDED"
                    if flip_level is None:
                        result["reason_codes"] = ["GAMMA_FLIP_ROOT_NOT_FOUND"]
                except Exception as paper_err:
                    logger.warning("Paper metrics unavailable for %s: %s", ticker, paper_err)

                return result
            except Exception as e:
                logger.error("gex_regime error: %s", e)
                return {"ticker": ticker.upper(), "status": "error", "error": str(e)}

        @self.router.reasoner(path="/signals/alerts", tags=["signal", "alerts"])
        async def scan_alerts(ticker: str = "SPY") -> dict[str, Any]:
            """Run full alert engine scan on a ticker."""
            from alert_engine import AlertEngine  # type: ignore

            try:
                engine = AlertEngine()
                summary = engine.get_alert_summary(ticker.upper())
                return {"ticker": ticker.upper(), "status": "ok", "summary": summary}
            except Exception as e:
                logger.error("scan_alerts error: %s", e)
                return {"ticker": ticker.upper(), "status": "error", "error": str(e)}

        @self.router.reasoner(path="/signals/vpin", tags=["signal", "vpin"])
        async def vpin_signal(ticker: str = "SPY") -> dict[str, Any]:
            """Return latest VPIN value from the ring buffer (no param needed)."""
            from services.vpin_engine import VpinEngine  # type: ignore

            try:
                engine = VpinEngine()
                val = engine.compute_vpin()
                return {"ticker": ticker.upper(), "status": "ok", "vpin": val}
            except Exception as e:
                return {"ticker": ticker.upper(), "status": "error", "error": str(e)}

        @self.router.reasoner(path="/signals/hawkes", tags=["signal", "hawkes"])
        async def hawkes_intensity(ticker: str = "SPY") -> dict[str, Any]:
            """Hawkes process state (mu, alpha, beta, cluster probability)."""
            from services.hawkes_process import HawkesProcess  # type: ignore

            try:
                model = HawkesProcess()
                state = model.get_state()
                return {"ticker": ticker.upper(), "status": "ok", "hawkes": state}
            except Exception as e:
                return {"ticker": ticker.upper(), "status": "error", "error": str(e)}

    # ──────────────────────────────────────────────────────────────────────
    #  Risk Management Reasoners
    # ──────────────────────────────────────────────────────────────────────
    def _register_risk_reasoners(self) -> None:
        @self.router.reasoner(path="/risk/portfolio-greeks", tags=["risk", "greeks"])
        async def portfolio_greeks(name: str = "main", spot: float = 0.0, iv: float = 0.15) -> dict[str, Any]:
            """Aggregate Greeks across a named portfolio."""
            from server import calc_portfolio_summary, db  # type: ignore

            portfolio = await db.portfolios.find_one({"name": name}, {"_id": 0})
            if not portfolio:
                return {"status": "error", "error": f"Portfolio '{name}' not found"}
            if spot > 0:
                summary = await calc_portfolio_summary(portfolio, spot, iv)
                return {"portfolio": name, "status": "ok", "summary": summary}
            return {"portfolio": name, "status": "ok", "raw": portfolio}

        @self.router.reasoner(path="/risk/scenario", tags=["risk", "scenario"])
        async def scenario_analysis(
            name: str = "main",
            spot_shock: float = 0.0,
            vol_shock: float = 0.0,
            time_decay_days: int = 1,
        ) -> dict[str, Any]:
            """What-if scenario analysis for a portfolio."""
            from server import calc_portfolio_scenario, db  # type: ignore

            portfolio = await db.portfolios.find_one({"name": name}, {"_id": 0})
            if not portfolio:
                return {"status": "error", "error": f"Portfolio '{name}' not found"}
            result = await calc_portfolio_scenario(
                portfolio,
                spot=portfolio.get("spot", 450.0) * (1 + spot_shock),
                iv=0.15 * (1 + vol_shock),
            )
            return {"portfolio": name, "status": "ok", "scenario": result}

        @self.router.reasoner(path="/risk/position-size", tags=["risk", "sizing"])
        async def position_size(
            account_size: float = 5000.0,
            risk_per_trade_pct: float = 0.02,
            spot: float = 0.0,
            gex_level: float = 0.0,
        ) -> dict[str, Any]:
            """Kelly-corrected position sizing based on account risk and GEX."""
            from portfolio import calc_position_size  # type: ignore

            try:
                result = calc_position_size(
                    account_size=account_size,
                    risk_per_trade_pct=risk_per_trade_pct,
                    spot=spot,
                    gex_level=gex_level,
                )
                return {"status": "ok", "sizing": result}
            except Exception as e:
                return {"status": "error", "error": str(e)}

    # ──────────────────────────────────────────────────────────────────────
    #  Briefing Reasoners
    # ──────────────────────────────────────────────────────────────────────
    def _register_briefing_reasoners(self) -> None:
        @self.router.reasoner(path="/briefing/build", tags=["briefing"])
        async def build_briefing(ticker: str = "SPY") -> dict[str, Any]:
            """Build a structured morning briefing."""
            from services.morning_briefing import build_briefing as _build  # type: ignore

            try:
                briefing = await _build(ticker.upper())
                return {"ticker": ticker.upper(), "status": "ok", "briefing": briefing}
            except Exception as e:
                logger.error("build_briefing error: %s", e)
                return {"ticker": ticker.upper(), "status": "error", "error": str(e)}

        @self.router.reasoner(path="/briefing/classify", tags=["briefing"])
        async def classify_regime(
            net_gex: float = 0.0,
            call_oi: float = 0,
            put_oi: float = 0,
            iv_skew: float = 0.0,
            flip_level: float = 0.0,
            spot: float = 0.0,
        ) -> dict[str, Any]:
            """Deterministic regime classification (BULLISH/BEARISH/NEUTRAL)."""
            from services.morning_briefing import classify_regime as _classify  # type: ignore

            regime = _classify(
                net_gex=net_gex,
                call_oi=call_oi,
                put_oi=put_oi,
                iv_skew=iv_skew,
                flip_level=flip_level,
                spot=spot,
            )
            return {"status": "ok", "regime": regime}

    # ──────────────────────────────────────────────────────────────────────
    #  Data Reasoners
    # ──────────────────────────────────────────────────────────────────────
    def _register_data_reasoners(self) -> None:
        @self.router.reasoner(path="/data/option-chain", tags=["data", "options"])
        async def option_chain(ticker: str = "SPY", max_expiries: int = 2) -> dict[str, Any]:
            """Fetch the current option chain with Greeks.

            DEAD-WIRE REPAIR. This used to import
            `services.yfinance_fetcher.fetch_option_chain`, which does not
            exist — that module is OHLCV-only (`fetch_underlying_ohlcv`,
            `fetch_and_store`, `get_latest_ticks`). The import was inside the
            `try`, so the failure was swallowed and the reasoner returned a
            generic error for every call.

            The canonical chain source is the Public adapter, which is
            data-only by construction (its own tests assert it never
            references an order method).
            """
            from services.public_api_adapter import fetch_chain_from_public_api

            try:
                expiries = max(1, min(int(max_expiries), 12))
            except (TypeError, ValueError):
                expiries = 2
            chain = await fetch_chain_from_public_api(ticker.upper(), max_expiries=expiries)
            if not chain or not chain.get("contracts"):
                # Reported, never zero-filled: an empty chain is not a chain
                # of zero exposures.
                return {
                    "ticker": ticker.upper(),
                    "status": "unavailable",
                    "reason": "NO_CHAIN_COVERAGE",
                }
            contracts = chain.get("contracts") or []
            return {
                "ticker": ticker.upper(),
                "status": "ok",
                "spot": chain.get("spot"),
                "expiries": chain.get("expiries") or [],
                "n_contracts": len(contracts),
                "data_source": chain.get("data_source"),
                "stale": chain.get("stale", False),
                "chain": contracts,
            }

        @self.router.reasoner(path="/data/vol-surface", tags=["data", "vol"])
        async def vol_surface(ticker: str = "SPY") -> dict[str, Any]:
            """Compute full IV surface (SABR/SVI interpolated)."""
            from services.stochastic_vol import VolSurfaceConstructor  # type: ignore

            try:
                svc = VolSurfaceConstructor()
                surface = await svc.build_surface(ticker.upper())
                return {"ticker": ticker.upper(), "status": "ok", "surface": surface}
            except Exception as e:
                return {"ticker": ticker.upper(), "status": "error", "error": str(e)}

    @staticmethod
    def _submit_order_refusal_payload() -> dict[str, Any]:
        """The fail-closed answer for /execute/order.

        Kept as its own method so the refusal contract can be pinned directly
        rather than only through whatever routing the hub happens to use.
        """
        logger.warning("agentfield /execute/order refused: no approved execution path")
        return {
            "status": "refused",
            "refused": True,
            "reason": "EXECUTION_PATH_NOT_APPROVED",
            "detail": (
                "The agentfield hub holds no approved broker path. Wiring "
                "this reasoner to a broker requires Nav's explicit "
                "approval; see CLAUDE.md 'Money path'."
            ),
            "requested": None,
            "submitted": False,
        }

    # ──────────────────────────────────────────────────────────────────────
    #  Execution Reasoners
    # ──────────────────────────────────────────────────────────────────────
    def _register_execution_reasoners(self) -> None:
        @self.router.reasoner(path="/execute/order", tags=["execution"])
        async def submit_order(order: dict[str, Any]) -> dict[str, Any]:
            """Refuse order submission. Always, and deterministically.

            DEAD-WIRE REPAIR, fail-closed. This used to import
            `services.paper_trader.PaperBroker`, a name that does not exist:
            `paper_trader` exports `PaperTrader`, and the `PaperBroker` class
            lives in `services/paper_broker.py`. The import sat INSIDE the
            `try`, so every call fell through to a generic error and the
            reasoner never reached a broker at all.

            Making that wire resolve would bring a NEW broker-reachable path
            into existence. CLAUDE.md forbids that without Nav's explicit
            approval -- "adding any new code path that reaches a real broker
            order" is on the forbidden list, and a paper submit still needs a
            reviewed, default-deny gate. So this refuses and says why, instead
            of importing a broker it has no approved way to use.
            """
            logger.debug("agentfield /execute/order invoked; refusing")
            payload = self._submit_order_refusal_payload()
            payload["requested"] = {
                "ticker": str(order.get("ticker", "")).upper() or None,
                "side": order.get("side"),
            }
            return payload

        @self.router.reasoner(path="/execute/health", tags=["execution", "health"])
        async def execution_health() -> dict[str, Any]:
            """Check execution engine health + cost tracker totals."""
            return {
                "status": "ok",
                "cost_total_usd": self.cost_tracker.total_cost_usd,
                "cost_total_tokens": self.cost_tracker.total_tokens,
                "agent_node_id": "floww-trading",
                "agent_version": "1.0.0",
            }

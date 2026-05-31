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
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ── AgentField SDK imports ────────────────────────────────────────────────
from agentfield import Agent, AgentRouter, AIConfig, CostTracker  # type: ignore

# ── Singleton ──────────────────────────────────────────────────────────────
_hub: Optional["AgentFieldHub"] = None


def get_hub() -> "AgentFieldHub":
    global _hub
    if _hub is None:
        _hub = AgentFieldHub()
    return _hub


async def init_hub() -> "AgentFieldHub":
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
        self.agent: Optional[Agent] = None
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
    def _register_signal_reasoners(self) -> None:
        @self.router.reasoner(path="/signals/gex-regime", tags=["signal", "gex"])
        async def gex_regime(ticker: str = "SPY") -> Dict[str, Any]:
            """Compute GEX regime for a ticker. Returns regime, flip level, walls."""
            from services.heatseeker import compute_gex_profile  # type: ignore

            try:
                profile = await compute_gex_profile(ticker)
                return {"ticker": ticker.upper(), "status": "ok", **profile}
            except Exception as e:
                logger.error("gex_regime error: %s", e)
                return {"ticker": ticker.upper(), "status": "error", "error": str(e)}

        @self.router.reasoner(path="/signals/alerts", tags=["signal", "alerts"])
        async def scan_alerts(ticker: str = "SPY") -> Dict[str, Any]:
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
        async def vpin_signal(ticker: str = "SPY") -> Dict[str, Any]:
            """Return latest VPIN value from the ring buffer (no param needed)."""
            from services.vpin_engine import VpinEngine  # type: ignore

            try:
                engine = VpinEngine()
                val = engine.compute_vpin()
                return {"ticker": ticker.upper(), "status": "ok", "vpin": val}
            except Exception as e:
                return {"ticker": ticker.upper(), "status": "error", "error": str(e)}

        @self.router.reasoner(path="/signals/hawkes", tags=["signal", "hawkes"])
        async def hawkes_intensity(ticker: str = "SPY") -> Dict[str, Any]:
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
        async def portfolio_greeks(name: str = "main", spot: float = 0.0, iv: float = 0.15) -> Dict[str, Any]:
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
        ) -> Dict[str, Any]:
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
        ) -> Dict[str, Any]:
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
        async def build_briefing(ticker: str = "SPY") -> Dict[str, Any]:
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
        ) -> Dict[str, Any]:
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
        async def option_chain(ticker: str = "SPY") -> Dict[str, Any]:
            """Fetch current option chain with Greeks."""
            from services.yfinance_fetcher import fetch_option_chain  # type: ignore

            try:
                chain = await fetch_option_chain(ticker.upper())
                return {"ticker": ticker.upper(), "status": "ok", "chain": chain}
            except Exception as e:
                return {"ticker": ticker.upper(), "status": "error", "error": str(e)}

        @self.router.reasoner(path="/data/vol-surface", tags=["data", "vol"])
        async def vol_surface(ticker: str = "SPY") -> Dict[str, Any]:
            """Compute full IV surface (SABR/SVI interpolated)."""
            from services.stochastic_vol import VolSurfaceConstructor  # type: ignore

            try:
                svc = VolSurfaceConstructor()
                surface = await svc.build_surface(ticker.upper())
                return {"ticker": ticker.upper(), "status": "ok", "surface": surface}
            except Exception as e:
                return {"ticker": ticker.upper(), "status": "error", "error": str(e)}

    # ──────────────────────────────────────────────────────────────────────
    #  Execution Reasoners
    # ──────────────────────────────────────────────────────────────────────
    def _register_execution_reasoners(self) -> None:
        @self.router.reasoner(path="/execute/order", tags=["execution"])
        async def submit_order(order: Dict[str, Any]) -> Dict[str, Any]:
            """Submit a paper order via PaperBroker.execute_signal."""
            from services.paper_trader import PaperBroker, Signal  # type: ignore

            try:
                broker = PaperBroker()
                signal = Signal(
                    ticker=order.get("ticker", "SPY"),
                    side=order.get("side", "buy").upper(),
                    order_type=order.get("order_type", "limit"),
                    quantity=order.get("quantity", 1),
                    price=order.get("price", 0.0),
                )
                result = broker.execute_signal(signal)
                return {"status": "ok", "result": result}
            except Exception as e:
                return {"status": "error", "error": str(e)}

        @self.router.reasoner(path="/execute/health", tags=["execution", "health"])
        async def execution_health() -> Dict[str, Any]:
            """Check execution engine health + cost tracker totals."""
            return {
                "status": "ok",
                "cost_total_usd": self.cost_tracker.total_cost_usd,
                "cost_total_tokens": self.cost_tracker.total_tokens,
                "agent_node_id": "floww-trading",
                "agent_version": "1.0.0",
            }

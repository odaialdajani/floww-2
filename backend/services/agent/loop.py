"""Reasoning loop (plan v3 L3): prefetch -> synthesise -> probe."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import time
import uuid
from typing import Any

from services.agent.access.horizon import is_prep_mode, normalize_horizon
from services.agent.budget import budget_state, record_spend
from services.agent.confluence import score as confluence_score
from services.agent.evidence import ev_id, substitute

SECTIONS = ["Structure", "Flow", "Levels", "Vol", "Company", "What changed", "Confluence", "Verdict", "Invalidation", "Trade"]
STANDARD_BUNDLE = ["gex_profile", "gex_grid", "vex_grid", "charm_grid", "flip_zones", "node_lifecycle", "air_pockets", "flow_live", "flow_regime", "alerts_feed", "time_delta"]


def _ledger_hash(ledger: dict[str, Any]) -> str:
    try:
        canon = json.dumps({k: str(v.get("value"))[:200] for k, v in ledger.items()}, sort_keys=True)
    except Exception:
        canon = str(sorted(ledger))
    return hashlib.sha256(canon.encode()).hexdigest()[:16]


async def run_turn(
    *,
    question: str,
    ticker: str,
    horizon: str = "all",
    question_class: str = "full-research",
    screen: dict[str, Any] | None = None,
    db=None,
    force_tier: str | None = None,
) -> dict[str, Any]:
    from services.agent import registry as reg

    # Ensure catalog is loaded (import side effect registers tools)
    with contextlib.suppress(Exception):
        import services.agent.tools  # noqa: F401

    t0 = time.time()
    horizon = normalize_horizon(horizon or (screen or {}).get("dte", "all"))
    ticker = (ticker or "SPY").upper()
    turn_id = str(uuid.uuid4())
    ledger: dict[str, dict[str, Any]] = {}
    events: list[dict[str, Any]] = []

    # Prefetch — one chain via cached path, pure bundle in parallel
    async def _call(name: str) -> None:
        tool = reg.get_tool(name)
        if tool is None or tool.fn is None:
            return
        events.append({"type": "step", "tool": name, "phase": "start"})
        try:
            env = await asyncio.wait_for(tool.fn(ticker, horizon=horizon), timeout=6)
        except Exception as e:
            env = {"status": "failed", "error": str(e), "source": "loop", "data": None}
        try:
            eid = ev_id(name, {"ticker": ticker, "horizon": horizon}, str(env.get("source", "")), str(env.get("as_of", "")))
            ledger[eid] = {"tool": name, "value": (env.get("data") if isinstance(env, dict) else env), "status": env.get("status", "ok") if isinstance(env, dict) else "ok", "source": env.get("source", "") if isinstance(env, dict) else ""}
        except Exception:
            pass
        events.append({"type": "step", "tool": name, "phase": "done"})

    await asyncio.gather(*[_call(n) for n in STANDARD_BUNDLE])

    # Confluence (deterministic)
    try:
        det = confluence_score({"flow": 0.0, "structure": 0.0, "microstructure": 0.0, "ml": 0.0, "vol": 0.0, "time_delta": 0.0, "inputs_status": {}})
    except Exception:
        det = {"total": 0.0, "direction": "neutral", "weights_version": "v1", "dimensions": {}}

    # Synthesise — one model call over the ledger only
    from services.agent import llm_client

    state = budget_state(db)
    if state.get("exhausted"):
        text = "Budget exhausted — deterministic read. " + _deterministic_read(ticker, horizon, ledger, det)
        status = "template"
        tier = "none"
    else:
        sys = "You are Lodestar, a market-structure research assistant. Cite evidence as {{evID}}. Never type a bare number for a factual claim. Sections: " + " | ".join(SECTIONS)
        prompt = f"Ticker {ticker} horizon {horizon}. Question: {question}\nLedger keys: {sorted(ledger)[:40]}\nConfluence: {det}\nPrep mode: {is_prep_mode()}"
        res = await llm_client.generate(prompt, system=sys, question_class=question_class, force_tier=force_tier)
        text = res.get("text", "") or _deterministic_read(ticker, horizon, ledger, det)
        status = res.get("status", "ok")
        tier = res.get("tier", "A")
        with contextlib.suppress(Exception):
            record_spend(float(res.get("est_cost_usd", 0.01)), db)

    rendered, flagged = substitute(text, ledger)
    verdict = {
        "ticker": ticker,
        "horizon": horizon,
        "direction": det.get("direction", "neutral"),
        "det_score": det.get("total", 0.0),
        "model_view": "agree",
        "disagreement": False,
        "weights_version": det.get("weights_version", "v1"),
        "ledger_hash": _ledger_hash(ledger),
        "status": status,
    }
    turn = {
        "turn_id": turn_id,
        "ticker": ticker,
        "horizon": horizon,
        "question": question,
        "question_class": question_class,
        "tier": tier,
        "status": status,
        "sections": SECTIONS,
        "text": rendered,
        "flagged": flagged,
        "ledger": ledger,
        "events": events,
        "verdict": verdict,
        "latency_s": round(time.time() - t0, 2),
        "prep_mode": is_prep_mode(),
    }
    # Persist turn (best effort) + write agent-owned structure snapshot
    try:
        if db is not None:
            db["agent_turns"].insert_one({"turn_id": turn_id, "ticker": ticker, "horizon": horizon, "events": events, "verdict": verdict})
            db["agent_structure_snapshots"].insert_one({"ticker": ticker, "ts": __import__("datetime").datetime.now(__import__("zoneinfo").ZoneInfo("America/New_York")), "ledger_hash": verdict["ledger_hash"]})
    except Exception:
        pass
    return turn


def _deterministic_read(ticker: str, horizon: str, ledger: dict, det: dict) -> str:
    keys = sorted(ledger)[:8]
    refs = " ".join("{{" + k + "}}" for k in keys)
    return f"<<S:Structure>> {ticker} {horizon} deterministic read. <<S:Confluence>> score {det.get('total', 0)} {det.get('direction', 'neutral')}. <<S:Verdict>> neutral, invalidation on flip loss. Evidence: {refs}"

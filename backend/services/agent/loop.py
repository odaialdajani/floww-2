"""Compatibility entry point; production work is owned by ResearchService."""

from services.agent.contracts import request_spec
from services.agent.read_budget import ReadBudget, budget_scope
from services.agent.research import deterministic_answer


async def run_turn(*, question, ticker, horizon="all", screen=None, reads=None, **kwargs):
    if reads is None:
        raise RuntimeError("Research requires an injected read-only data source")
    spec = request_spec(dict(question=question, ticker=ticker, horizon=horizon, screen=screen))
    budget = ReadBudget()
    with budget_scope(budget, spec):
        snapshots = [await reads.snapshot(t, spec["horizon"], price_only=spec.get("price_only", False))
                     for t in spec["tickers"]]
    return {
        "ticker": spec["ticker"],
        "horizon": spec["horizon"],
        "status": "preview",
        "saved": False,
        "read_activity": budget.close(),
        "answer": deterministic_answer(snapshots, spec),
    }

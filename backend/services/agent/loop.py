"""Compatibility entry point; production work is owned by ResearchService."""

from services.agent.contracts import request_spec
from services.agent.research import deterministic_answer


async def run_turn(*, question, ticker, horizon="all", screen=None, reads=None, **kwargs):
    if reads is None:
        raise RuntimeError("Research requires an injected read-only data source")
    spec = request_spec(dict(question=question, ticker=ticker, horizon=horizon, screen=screen))
    snapshots = [await reads.snapshot(t, spec["horizon"]) for t in spec["tickers"]]
    return {
        "ticker": spec["ticker"],
        "horizon": spec["horizon"],
        "status": "preview",
        "saved": False,
        "answer": deterministic_answer(snapshots, spec),
    }

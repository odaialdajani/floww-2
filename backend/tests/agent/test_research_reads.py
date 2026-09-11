from datetime import UTC, datetime

import pytest

from services.agent.reads import ResearchReads
from services.agent.research import deterministic_answer

NOW = datetime(2026, 9, 11, 15, tzinfo=UTC)


def chain(kind="C"):
    return {
        "spot": 100,
        "event_time": NOW.isoformat(),
        "contracts": [{"strike": 100, "type": kind, "gamma": 0.01, "open_interest": 10, "expiry": "2026-09-11"}],
    }


@pytest.mark.asyncio
async def test_real_calculator_values_change_without_neutralizing_missing_inputs():
    snapshots = []
    for kind in ("C", "P"):
        reads = ResearchReads(lambda *a, kind=kind: chain(kind), lambda *a: None, lambda *a: [])
        snapshot = await reads.snapshot("SPY", "all", now=NOW)
        snapshots.append(snapshot)
    values = [
        next(f["value"] for f in s["facts"] if f["metric"] == "Total estimated gamma exposure") for s in snapshots
    ]
    assert values == [1000, -1000]
    spec = {"tickers": ["SPY"], "screen": {}}
    answer = deterministic_answer([snapshots[0]], spec)
    assert "1,000" in answer["sections"][0]["text"]
    assert answer["claim_status"] == "non-gradeable"


@pytest.mark.asyncio
async def test_alert_failure_differs_from_empty_and_unknown_time_is_preserved():
    def failed(ticker):
        raise RuntimeError("store down")

    reads = ResearchReads(lambda *a: {}, lambda *a: None, failed)
    snapshot = await reads.snapshot("SPY", "all", now=NOW)
    assert snapshot["alerts_status"] == "error"
    assert snapshot["observed_at"] is None
    assert all(f["status"] == "degraded" for f in snapshot["facts"])


@pytest.mark.asyncio
async def test_datetime_alerts_and_chain_dates_are_supported_without_relabelling():
    reads = ResearchReads(
        lambda *a: chain(),
        lambda *a: None,
        lambda *a: [{"asof_ts": NOW, "expiry": "2026-09-11", "bias": "BULLISH", "conviction": 80}],
    )
    snapshot = await reads.snapshot("SPY", "0dte", now=NOW)
    assert snapshot["flow"] == [0.8]

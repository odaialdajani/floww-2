"""Finite fixture read through actual admission/answer modules; not a live API server."""
import asyncio
import json
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def answer(packet, body, range_transport=None):
    from services.agent.contracts import request_spec
    from services.agent.plan_draft import build_plan_draft
    from services.agent.reads import ResearchReads
    from services.agent.research import deterministic_answer
    from services.solstice_replay import recorded_display

    attempts = []

    def forbidden(*args, **kwargs):
        attempts.append("provider/live substitute")
        raise AssertionError("Fixture research must read owning records only")

    spec = request_spec(body)
    records = {}
    for rep in (packet["replay"], packet["baseline"]):
        snap = rep["snapshot"]
        records[(snap["ticker"], snap["snapshot_id"])] = recorded_display(rep,snap["ticker"],snap["snapshot_id"])
    range_records = (range_transport or {}).get("records", {})
    reads = ResearchReads(forbidden,forbidden,forbidden,read_daily_bars=forbidden,
                          read_recorded_map=lambda ticker,sid:records.get((ticker,sid)),
                          read_recorded_range=lambda ticker,rid:range_records.get(rid)
                          if range_records.get(rid, {}).get("ticker") == ticker else None)
    with patch.object(socket.socket,"connect",forbidden), patch.object(socket.socket,"connect_ex",forbidden):
        snapshot = asyncio.run(reads.snapshot(spec["ticker"],spec["horizon"],screen=spec["screen"],now=datetime.now(UTC)))
    assert not attempts, "A forbidden seam was called, even if swallowed"
    result = deterministic_answer([snapshot],spec)
    turn_id = "r18-range-fixture-answer" if spec["screen"].get("displayMode") == "range-replay" else "r15-fixture-answer"
    result["plan_draft"] = build_plan_draft(result, turn_id)
    return dict(turn_id=turn_id,status="completed",saved=False,ticker=spec["ticker"],horizon=spec["horizon"],
                question=spec["question"],answer=result)


if __name__ == "__main__":
    packet = json.loads(Path(sys.argv[1]).read_text())
    range_transport = json.loads(Path(sys.argv[2]).read_text()) if len(sys.argv) > 2 else None
    print(json.dumps(answer(packet,json.load(sys.stdin),range_transport),allow_nan=False,default=str))

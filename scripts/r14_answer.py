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


def answer(packet, body):
    from services.agent.contracts import request_spec
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
    reads = ResearchReads(forbidden,forbidden,forbidden,read_daily_bars=forbidden,
                          read_recorded_map=lambda ticker,sid:records.get((ticker,sid)))
    # Windows creates an internal socket pair when the event loop starts.
    # Start the loop first, then keep every connection forbidden during reads.
    with asyncio.Runner() as runner:
        runner.get_loop()
        with patch.object(socket.socket,"connect",forbidden), patch.object(socket.socket,"connect_ex",forbidden):
            snapshot = runner.run(reads.snapshot(spec["ticker"],spec["horizon"],screen=spec["screen"],now=datetime.now(UTC)))
    assert not attempts, "A forbidden seam was called, even if swallowed"
    result = deterministic_answer([snapshot],spec)
    return dict(turn_id="r14-fixture-answer",status="completed",saved=False,ticker=spec["ticker"],horizon=spec["horizon"],
                question=spec["question"],answer=result)


if __name__ == "__main__":
    packet = json.loads(Path(sys.argv[1]).read_text())
    print(json.dumps(answer(packet,json.load(sys.stdin)),allow_nan=False,default=str))

"""Controlled real-TCP progress proof; no provider, model, real account or server startup."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import time
import uuid
from contextlib import AsyncExitStack, ExitStack
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI
from mongomock_motor import AsyncMongoMockClient

from routes.agent import router
from scripts.research_eval_metrics import CaseTrace, observe_progress_stream, read_metrics, saved_progress_metrics
from services.agent.reads import ResearchReads
from services.agent.repository import AgentRepository
from services.agent.research import ResearchService


async def verify():
    def restore_env(key, value):
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    with ExitStack() as cleanup:
        for key in ("FLOWW_AGENT_DEPLOYMENT", "FLOWW_AGENT_ORIGINS"):
            cleanup.callback(restore_env, key, os.environ.get(key))
        async with AsyncExitStack() as async_cleanup:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            cleanup.callback(sock.close)
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
            sock.listen(16)
            sock.setblocking(False)
            base = f"http://127.0.0.1:{port}"
            os.environ["FLOWW_AGENT_DEPLOYMENT"] = "local"
            os.environ["FLOWW_AGENT_ORIGINS"] = base
            repo = AgentRepository(AsyncMongoMockClient(tz_aware=True).measurement_fixture)
            await repo.initialize()

            def chain(*args):
                time.sleep(0.35)
                return {"spot": 100, "contracts": [], "source": "CONTROLLED PROGRESS FIXTURE"}

            service = ResearchService(repo, ResearchReads(chain, lambda *a: None, lambda *a: []))
            async_cleanup.push_async_callback(service.close)
            app = FastAPI()
            app.include_router(router)
            app.state.research_service = service
            server = uvicorn.Server(
                uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", proxy_headers=False, lifespan="off")
            )
            worker = asyncio.create_task(server.serve(sockets=[sock]))
            original_connect = socket.socket.connect
            original_connect_ex = socket.socket.connect_ex
            cleanup.callback(setattr, socket.socket, "connect", original_connect)
            cleanup.callback(setattr, socket.socket, "connect_ex", original_connect_ex)

            async def stop_server():
                server.should_exit = True
                await asyncio.wait_for(worker, 3)

            async_cleanup.push_async_callback(stop_server)
            blocked = []

            def guard(sock, address):
                if not isinstance(address, tuple) or address[:2] != ("127.0.0.1", port):
                    blocked.append("non-fixture connection")
                    raise AssertionError("Only the owned fixture listener is allowed")
                return original_connect(sock, address)

            def guard_ex(sock, address):
                if not isinstance(address, tuple) or address[:2] != ("127.0.0.1", port):
                    blocked.append("non-fixture connection")
                    raise AssertionError("Only the owned fixture listener is allowed")
                return original_connect_ex(sock, address)

            async with asyncio.timeout(3):
                while not server.started:
                    await asyncio.sleep(0.005)
            socket.socket.connect = guard
            socket.socket.connect_ex = guard_ex
            async with httpx.AsyncClient(base_url=base, headers={"Origin": base}, trust_env=False) as client:
                assert (await client.post("/api/agent/session")).status_code == 200
                trace = CaseTrace()
                trace.mark("request_started")
                admitted = await client.post(
                    "/api/agent/ask",
                    json={
                        "question": "What is the spot price of SPY?",
                        "request_id": f"{int(time.time() * 1000)}-{uuid.uuid4()}",
                    },
                )
                assert admitted.status_code == 200, admitted.text
                trace.mark("admission_received")
                turn_id = admitted.json()["turn_id"]
                terminal = await observe_progress_stream(client, turn_id, trace, timeout=4)
                trace.mark("answer_lookup_started")
                saved = (await client.get("/api/agent/turn/" + turn_id)).json()
                trace.mark("saved_answer_received")
                repeated = (await client.get("/api/agent/turn/" + turn_id)).json()
                assert repeated == saved and terminal["status"] == "completed"
                trace.mark("verification_finished")
                trace.finish()
                measured = trace.snapshot()
                marks = measured["timings_s"]
                assert marks["first_stream_progress_received"] < marks["terminal_stream_received"]
                assert marks["terminal_stream_received"] <= marks["saved_answer_received"] <= marks["verification_finished"]
                assert read_metrics(saved)["started"] == 1
                assert measured["model_invocations"] == 0 and not blocked
                return dict(
                    status="CONTROLLED_TCP_MEASUREMENT_PASSED",
                    trace=measured,
                    reads=read_metrics(saved),
                    saved_progress=saved_progress_metrics(saved),
                    blocked_external_attempts=len(blocked),
                    fixture="Synthetic delayed cached price; in-memory owned research store; actual production research routes",
                    limitations=[
                        "No live model/provider request",
                        "Client event receipt is not browser display or first paint",
                        "Not fresh held-out acceptance",
                    ],
                )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Output exists; choose a new result path")
    result = asyncio.run(verify())
    with args.output.open("x", encoding="utf-8") as target:
        json.dump(result, target, indent=2, allow_nan=False)
        target.write("\n")
    print(json.dumps(result, indent=2))

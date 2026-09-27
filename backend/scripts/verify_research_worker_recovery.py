"""Exercise actual research startup/service/routes across an owned abrupt exit.

Synthetic cache and model transport only. Real local Mongo storage is isolated;
no production collection, model dispatch, provider, order, or app restart.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREFIX = "research_worker_recovery_"
SOURCES = [
    "backend/server.py", "backend/routes/agent.py", "backend/services/agent/repository.py",
    "backend/services/agent/research.py", "backend/services/agent/reads.py",
    "backend/services/agent/read_budget.py", "backend/services/agent/codex_model.py",
    "backend/services/agent/contracts.py", "backend/services/agent/local_access.py",
    "backend/scripts/verify_research_worker_recovery.py",
]
SETTINGS = {"model": "RECOVERY_FIXTURE_ONLY", "effort": "medium", "speed": "default"}


def identities():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES}


def exclusive_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def guarded_environment(name):
    if not re.fullmatch(PREFIX + r"[a-f0-9]{32}", name):
        raise ValueError("Only a newly named isolated recovery store is allowed")
    os.environ.update(MONGO_URL="mongodb://127.0.0.1:27017", DB_NAME=name,
                      FLOWW_AGENT_DEPLOYMENT="local", FLOWW_AGENT_DISABLED="0",
                      DUCKDB_PATH=":memory:")
    attempts = []
    connect, connect_ex = socket.socket.connect, socket.socket.connect_ex
    getaddrinfo = socket.getaddrinfo

    def allowed(address):
        return (isinstance(address, tuple) and len(address) >= 2
                and address[0] in {"127.0.0.1", "::1"} and address[1] == 27017)

    def refuse(kind):
        attempts.append(kind)
        raise RuntimeError("Recovery proof forbids external network and child programs")

    def checked_connect(sock, address):
        if not allowed(address):
            refuse("socket")
        return connect(sock, address)

    def checked_connect_ex(sock, address):
        if not allowed(address):
            refuse("socket_ex")
        return connect_ex(sock, address)

    def checked_lookup(host, *args, **kwargs):
        if host not in {None, "localhost", "127.0.0.1", "::1"}:
            refuse("dns")
        return getaddrinfo(host, *args, **kwargs)

    socket.socket.connect = checked_connect
    socket.socket.connect_ex = checked_connect_ex
    socket.getaddrinfo = checked_lookup
    subprocess.Popen = lambda *args, **kwargs: refuse("subprocess")
    return attempts


async def wait_for(check, *, seconds=15):
    async with asyncio.timeout(seconds):
        while True:
            value = await check()
            if value:
                return value
            await asyncio.sleep(.02)


async def child(name, phase, receipt):
    # PyMongo reads Windows version metadata on import. Use the real kernel
    # version directly so platform does not spawn a visible cmd.exe helper.
    if os.name == "nt":
        import platform

        version = sys.getwindowsversion()
        platform._syscmd_ver = lambda *args, **kwargs: (
            "Windows", "Microsoft Windows", ".".join(map(str, version.platform_version))
        )
    attempts = guarded_environment(name)
    # Guard the actual managed-login transport before importing composition.
    from services.agent.codex_bridge import CodexBridge

    async def no_real_bridge(*args, **kwargs):
        attempts.append("real_bridge")
        raise RuntimeError("Real model transport is forbidden")

    CodexBridge.__aenter__ = no_real_bridge
    import httpx

    import server
    from services.agent.contracts import canonical
    from services.agent.local_access import COOKIE
    from services.agent.reads import ResearchReads
    from services.duckdb_engine import db as analytics_db

    assert os.environ["DUCKDB_PATH"] == ":memory:"
    assert all(not row[2] for row in analytics_db.conn.execute("PRAGMA database_list").fetchall())
    database = server.db
    if database.name != name:
        raise AssertionError("Composition selected a different store")
    if phase == "crash" and await database.list_collection_names():
        raise AssertionError("Initial recovery store must be empty")
    await server.startup_research()
    service = server.app.state.research_service
    if service is None:
        raise AssertionError("Actual research startup failed")
    counts = {"cache": 0, "fixture_answer": 0, "fixture_catalog": 0}

    def peek_chain(ticker, preferred):
        counts["cache"] += 1
        observed = datetime.now(UTC).isoformat()
        return {"ticker": ticker, "spot": 123.45, "contracts": [],
                "event_time": observed, "spot_event_time": observed,
                "source": "SYNTHETIC RECOVERY FIXTURE", "spot_source": "SYNTHETIC RECOVERY FIXTURE"}

    service.reads = ResearchReads(peek_chain, lambda *_: None, lambda *_: [])

    class FixtureBridge:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def catalog(self):
            counts["fixture_catalog"] += 1
            return [{"id": SETTINGS["model"], "efforts": ["medium"], "speeds": ["default"]}]

        async def answer(self, content, settings, answer_shape):
            counts["fixture_answer"] += 1
            if phase != "crash":
                raise AssertionError("Restart must not repeat the model boundary")
            body = json.loads(content)
            question = body["question"]
            await database.recovery_fixture_dispatches.insert_one({"question": question, "fixture_only": True})
            if "completed example" not in question:
                await asyncio.Event().wait()
            fact = next(item for item in body["facts"] if item["metric"] == "Underlying price")
            return ({"sections": [{"name": "Market", "fact_ids": [fact["id"]], "interpretation": "limited"}],
                     "relationships": [], "explanations": []},
                    {"fixture_only": True}, "fixture-thread", "fixture-answer")

    service.model.bridge_factory = FixtureBridge
    headers = {"Origin": "http://localhost:8000"}
    transport = httpx.ASGITransport(app=server.app, client=("127.0.0.1", 11111))

    def new_body(question):
        return {"request_id": str(int(time.time() * 1000)) + "-" + str(uuid.uuid4()),
                "ticker": "SPY", "question": question, "horizon": "all",
                "screen": {"ticker": "SPY", "page": "heatseeker"}}

    if phase == "crash":
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost:8000", headers=headers) as client:
            response = await client.post("/api/agent/session")
            assert response.status_code == 200, response.text
            capability = client.cookies[COOKIE]
            owner = await service.repository.owner(capability)
            response = await client.put("/api/agent/prefs", json={"ai_settings": SETTINGS})
            assert response.status_code == 200, response.text
            bodies = [new_body("Explain SPY structure for the completed example"),
                      new_body("Explain SPY structure for interrupted example one"),
                      new_body("Explain SPY structure for interrupted example two"),
                      new_body("Explain SPY structure for the queued example")]
            response = await client.post("/api/agent/ask", json=bodies[0])
            assert response.status_code == 200, response.text
            ids = [response.json()["turn_id"]]
            async def completed():
                row = await service.repository.read(owner, ids[0])
                return row if row["status"] == "completed" else None
            first = await wait_for(completed)
            assert first["answer"]["mode"] == "model-assisted"
            assert first["answer"]["facts"][0]["value"] == 123.45
            for body in bodies[1:]:
                response = await client.post("/api/agent/ask", json=body)
                assert response.status_code == 200, response.text
                ids.append(response.json()["turn_id"])
            async def two_active():
                return await database.recovery_fixture_dispatches.count_documents({}) == 3
            await wait_for(two_active)
            rows = [await service.repository.read(owner, key) for key in ids]
            assert [row["status"] for row in rows] == ["completed", "running", "running", "queued"]
            usage = await service.model.spend.state()
            assert usage["calls"] == 3 and usage["actual_cost"] is None
            assert not attempts
            probe = {"_id": "owned-recovery", "owner": owner, "capability": capability,
                     "bodies": bodies, "ids": ids, "completed_answer": first["answer"],
                     "events_before": [len(row["events"]) for row in rows],
                     "counts_before": counts, "usage_before": usage,
                     "states_before": [row["status"] for row in rows]}
            await database.recovery_probe.insert_one(probe)
            exclusive_json(receipt, {"state": "ready_for_owned_abrupt_exit", "store": name,
                "states": probe["states_before"], "calls": usage["calls"], "counts": counts,
                "real_model_calls": 0, "external_attempts": attempts})
            # Abrupt termination of ONLY this newly spawned proof process. No
            # shutdown callback, task cancellation, client close or finally.
            os._exit(73)
    probe = await database.recovery_probe.find_one({"_id": "owned-recovery"})
    if probe is None:
        raise AssertionError("Missing owned crash boundary evidence")
    rows = [await service.repository.read(probe["owner"], key) for key in probe["ids"]]
    assert [row["status"] for row in rows] == ["completed", "interrupted", "interrupted", "interrupted"]
    assert canonical(rows[0]["answer"]) == canonical(probe["completed_answer"])
    for index, row in enumerate(rows[1:], 1):
        assert row["answer"] is None
        assert len(row["events"]) == probe["events_before"][index] + 1
        assert row["events"][-1]["status"] == "interrupted"
        if row.get("read_activity") is not None:
            assert row["read_activity"]["closed"] is True
    usage_before = await service.model.spend.state()
    assert usage_before["calls"] == probe["usage_before"]["calls"] == 3
    day = await database.agent_oauth_usage.find_one({"_id": "day:" + datetime.now(UTC).date().isoformat()})
    statuses = sorted(entry["status"] for entry in day["entries"].values())
    assert statuses == ["completed", "uncertain", "uncertain"]
    assert await database.recovery_fixture_dispatches.count_documents({}) == 3
    assert not service.tasks and counts["fixture_answer"] == counts["cache"] == 0
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost:8000", headers=headers,
                                 cookies={COOKIE: probe["capability"]}) as client:
        history = await client.get("/api/agent/history")
        assert history.status_code == 200, history.text
        assert {row["turn_id"] for row in history.json()["turns"]} == set(probe["ids"])
        for index, key in enumerate(probe["ids"]):
            response = await client.get("/api/agent/turn/" + key)
            assert response.status_code == 200
            assert response.json()["status"] == rows[index]["status"]
            stream = await client.get("/api/agent/stream/" + key,
                                      headers={"Last-Event-ID": str(probe["events_before"][index])})
            assert stream.status_code == 200
            if index:
                assert stream.text.count("event: error") == 1 and '"status": "interrupted"' in stream.text
            else:
                assert stream.text == ""
            replay = await client.post("/api/agent/ask", json=probe["bodies"][index])
            assert replay.status_code == 200
            assert replay.json() == {"turn_id": key, "status": rows[index]["status"]}
        assert not service.tasks and counts["fixture_answer"] == counts["cache"] == 0
        changed = {**probe["bodies"][0], "question": "Explain QQQ instead"}
        assert (await client.post("/api/agent/ask", json=changed)).status_code == 409
        os.environ["FLOWW_AGENT_DISABLED"] = "1"
        assert (await client.post("/api/agent/ask", json=new_body("What is the SPY spot price?"))).status_code == 503
        assert (await client.get("/api/agent/history")).status_code == 200
        os.environ["FLOWW_AGENT_DISABLED"] = "0"
        new_turn = await client.post("/api/agent/ask", json=new_body("What is the SPY spot price?"))
        assert new_turn.status_code == 200, new_turn.text
        fresh_id = new_turn.json()["turn_id"]
        async def fresh_completed():
            row = await service.repository.read(probe["owner"], fresh_id)
            return row if row["status"] == "completed" else None
        fresh = await wait_for(fresh_completed)
        assert fresh["answer"]["facts"][0]["value"] == 123.45
        assert fresh["answer"]["mode"] == "deterministic"
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost:8000", headers=headers) as outsider:
        assert (await outsider.post("/api/agent/session")).status_code == 200
        assert (await outsider.get("/api/agent/history")).json() == {"turns": []}
        for key in probe["ids"]:
            assert (await outsider.get("/api/agent/turn/" + key)).status_code == 404
            assert (await outsider.get("/api/agent/stream/" + key)).status_code == 404
            assert (await outsider.post("/api/agent/cancel/" + key)).status_code == 404
    assert (await service.model.spend.state())["calls"] == 3
    assert await database.recovery_fixture_dispatches.count_documents({}) == 3
    assert counts["fixture_answer"] == 0 and counts["cache"] == 1
    assert not attempts
    # Re-initialization is idempotent: already-terminal event logs do not grow.
    await service.repository.initialize()
    after = [await service.repository.read(probe["owner"], key) for key in probe["ids"]]
    assert [row["events"] for row in after] == [row["events"] for row in rows]
    await server.shutdown_research()
    exclusive_json(receipt, {"status": "passed", "store": name,
        "states_before": probe["states_before"], "states_after": [row["status"] for row in rows],
        "checks": ["actual_research_startup", "real_worker_owned_abrupt_exit", "exact_completed_answer",
                   "queued_and_active_interrupted_once", "saved_history_and_cursor_resume", "same_request_no_repeat",
                   "changed_request_conflict", "disabled_new_work_retains_history", "new_factual_work_after_restart",
                   "foreign_owner_isolation", "uncertain_usage_retained", "reinitialize_idempotent"],
        "fixture_calls_before": 3, "fixture_calls_after": 3, "usage_statuses": statuses,
        "restart_counts": counts, "real_model_calls": 0, "external_attempts": attempts,
        "completed_answer_sha256": hashlib.sha256(canonical(rows[0]["answer"]).encode()).hexdigest()})
    server.client.close()


def verify(output):
    output = output.resolve()
    if not output.is_relative_to(ROOT / "output"):
        raise ValueError("Recovery proof output must be a new directory below project output")
    output.mkdir(parents=True, exist_ok=False)
    before = identities()
    name = PREFIX + uuid.uuid4().hex
    exclusive_json(output / "initial.json", {"store": name, "sources": before,
                                            "scope": "isolated worker recovery; synthetic cache/model"})
    results = []
    for phase, expected in [("crash", 73), ("recover", 0)]:
        command = [sys.executable, "-m", "scripts.verify_research_worker_recovery",
                   "--child", phase, "--database", name, "--receipt", str(output / (phase + ".json"))]
        result = subprocess.run(command, cwd=ROOT / "backend", capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=60,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        (output / (phase + ".stdout.log")).write_text(result.stdout, encoding="utf-8")
        (output / (phase + ".stderr.log")).write_text(result.stderr, encoding="utf-8")
        results.append({"phase": phase, "exit": result.returncode, "expected": expected})
        if result.returncode != expected:
            exclusive_json(output / "result.json", {"status": "failed", "processes": results,
                                                     "sources_unchanged": before == identities()})
            raise RuntimeError("Owned recovery child failed; inspect preserved logs")
    recovered = json.loads((output / "recover.json").read_text(encoding="utf-8"))
    unchanged = before == identities()
    exclusive_json(output / "result.json", {"status": "passed" if unchanged else "source_changed",
        "sources": before, "sources_unchanged": unchanged, "processes": results, "recovery": recovered,
        "limits": ["Local isolated MongoDB remains running; this is not database crash recovery or production backup proof",
                   "Only actual research startup/shutdown callbacks run, not full application lifespan/background workers",
                   "External cached-data and model-transport seams are synthetic; no real upstream model dispatch",
                   "Routes use the real application through in-process HTTP transport, not a listening server or browser",
                   "Descriptive answers only; prediction projection and paper/live lifecycles are not covered"]})
    if not unchanged:
        raise RuntimeError("Sources changed during proof")
    print(json.dumps({"status": "passed", "report": str(output / "result.json")}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--child", choices=["crash", "recover"])
    parser.add_argument("--database")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    if args.child:
        if not args.receipt or not args.receipt.resolve().is_relative_to(ROOT / "output"):
            parser.error("Child receipt must be below project output")
        asyncio.run(child(args.database, args.child, args.receipt))
    elif args.run and args.output:
        verify(args.output)
    else:
        parser.error("Use --run --output <new directory>")


if __name__ == "__main__":
    main()

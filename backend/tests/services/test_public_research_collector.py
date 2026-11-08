"""Fixed Public research capture contracts: synthetic bytes, real private journal/budget."""
import asyncio
import copy
import hashlib
import importlib
import json
import subprocess
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from services.public_budget import PublicBudget
from services.public_research_store import ResearchRefusal, ResearchStore

AT = datetime(2026, 11, 6, 15, tzinfo=UTC)


def module():
    try:
        value = importlib.import_module("services.public_research_collector")
    except ModuleNotFoundError as exc:
        if exc.name != "services.public_research_collector":
            raise
        value = None
    assert value is not None, "bounded raw collector is not implemented"
    return value


class Clock:
    def __init__(self, now=AT):
        self.wall = now
        self.mono = 1000.0

    def now(self):
        return self.wall

    def monotonic(self):
        return self.mono

    def advance(self, seconds):
        self.wall += timedelta(seconds=seconds)
        self.mono += seconds


class Pacer:
    def __init__(self, action=None):
        self.action = action

    async def wait(self):
        if self.action:
            self.action()


class Budget(PublicBudget):
    def __init__(self, max_inflight=2):
        super().__init__(capacity=20, refill_per_sec=0, max_inflight=max_inflight)
        self.releases = 0

    def release(self):
        self.releases += 1
        super().release()


def body_for(request):
    if request.kind == "quotes":
        value = {"quotes": [{"instrument": {"symbol": request.symbol, "type": "EQUITY"},
                            "bid": 500, "ask": 500.1, "bidSize": "2", "askSize": None,
                            "bidTimestamp": "2026-11-06T14:59:58+00:00"}]}
    elif request.kind == "expirations":
        value = {"expirations": ["2026-11-13", "2026-11-20"]}
    else:
        compact = request.expiry[2:].replace("-", "")
        value = {"calls": [{"instrument": {"symbol": request.symbol + compact + "C00500000"},
                             "bid": "1.20", "ask": "1.30", "bidSize": "2", "askSize": False,
                             "bidTimestamp": "2026-11-06T14:59:57+00:00",
                             "optionDetails": {"greeks": {"delta": "0.5"}}}], "puts": []}
    return json.dumps(value, separators=(",", ":")).encode()


class Transport:
    def __init__(self, m, store, clock, change=None):
        self.m, self.store, self.clock, self.change = m, store, clock, change
        self.calls = []

    @asynccontextmanager
    async def open(self, request, attempt_id):
        rows = self.store.attempts("cycle-1")
        assert any(row["attempt_id"] == attempt_id and row["status"] == "dispatching" for row in rows)
        self.calls.append(request)
        body = body_for(request)
        values = {"http_status": 200, "source_delivery": "network",
                  "media_type": "json", "content_encoding": "identity", "retry_after": None}
        if self.change:
            changed = self.change(request, body, values)
            if changed is not None:
                body = changed
        async def chunks():
            for start in range(0, len(body), 65536):
                yield body[start:start + 65536]
        yield self.m.RawReply(chunks=chunks(), **values)


def make(m, store, transport, clock, budget=None, gate=None, pacer=None, stop=None):
    return m.ResearchCollector(store=store, transport=transport, budget=budget or Budget(),
                               clock=clock, session_gate=gate or (lambda now: True),
                               pacer=pacer or Pacer(), should_stop=stop or (lambda: False))


@pytest.mark.asyncio
async def test_exact_raw_responses_unknown_authority_and_distinct_expiry_receipts(tmp_path):
    m = module()
    clock = Clock()
    plan = m.build_plan(["2026-11-13", "2026-11-20"])
    with ResearchStore(tmp_path / "research", plan) as store:
        def delay(request, body, values):
            if request.kind == "chain":
                clock.advance(2)
        transport = Transport(m, store, clock, delay)
        result = await make(m, store, transport, clock).capture_cycle("cycle-1")
        assert result["status"] == "committed"
        assert result["dispatch_attempts"] == 8
        assert result["research_only"] is True and result["executable"] is False
        assert [request.kind for request in transport.calls] == [
            "quotes", "expirations", "chain", "chain", "quotes", "expirations", "chain", "chain"]
        assert {request.symbol for request in transport.calls} == {"SPY", "QQQ"}
        chains = [row for row in store.attempts("cycle-1") if row["request"]["kind"] == "chain"]
        assert [row["response"]["body_completed_at"] for row in chains] == [
            "2026-11-06T15:00:02+00:00", "2026-11-06T15:00:04+00:00",
            "2026-11-06T15:00:06+00:00", "2026-11-06T15:00:08+00:00"]
        first = chains[0]
        assert first["body"] == body_for(transport.calls[2])
        row = store.observations(first["attempt_id"])[0]
        assert row["response_sha256"] == hashlib.sha256(first["body"]).hexdigest()
        assert row["raw_side"] == "calls" and row["raw_index"] == 0
        assert row["contract"]["bid_size"] == 2 and row["contract"]["ask_size"] is None
        assert row["raw_sizes"] == {"bidSize": "2", "askSize": False}
        assert row["contract"]["bid_timestamp"] == "2026-11-06T14:59:57+00:00"
        assert row["contract"]["ask_timestamp"] is None
        assert row["greeks_event_time"] is None
        assert row["multiplier"] is None and row["adjusted"] is None
        assert row["contract"]["oi_effective_date"] is None
        calls = len(transport.calls)
        assert await make(m, store, transport, clock).capture_cycle("cycle-1") == result
        assert len(transport.calls) == calls


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["invalid_json", "sensitive", "overflow", "invalid_utf8", "compressed"])
async def test_raw_provenance_explicitly_distinguishes_parse_failure_and_withholding(tmp_path, case):
    m = module()
    clock = Clock()
    plan = m.build_plan(["2026-11-13"], m.Limits(max_body_bytes=512))
    def change(request, body, values):
        if request.kind != "chain":
            return body
        if case == "invalid_json":
            return b'{"broken":'
        if case == "sensitive":
            return b'{"nested":{"accessToken":"synthetic-never-store"}}'
        if case == "overflow":
            return b"x" * 513
        if case == "invalid_utf8":
            return b"\xff"
        values["content_encoding"] = "unsupported"
        return b"compressed-fixture"
    with ResearchStore(tmp_path / "research", plan) as store:
        transport = Transport(m, store, clock, change)
        result = await make(m, store, transport, clock).capture_cycle("cycle-1")
        chains = [r for r in store.attempts("cycle-1") if r["request"]["kind"] == "chain"]
        assert chains and result["has_gaps"] is True
        for row in chains:
            if case == "invalid_json":
                assert row["body"] == b'{"broken":'
                assert row["parsed"]["status"] == "parse_failed"
                assert row["response"]["body_complete"] is True
            else:
                assert row["body"] == b""
                assert row["response"]["withholding_reason"] is not None
                assert store.observations(row["attempt_id"]) == []
                if case == "overflow":
                    assert row["response"]["source_body_sha256"] is None
                    assert row["response"]["body_complete"] is False
        assert b"synthetic-never-store" not in (tmp_path / "research" / "collector.sqlite3").read_bytes()


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["wrong_root", "wrong_expiry", "trailing_osi", "nan", "infinite", "boolean_greek"])
async def test_existing_parser_is_wrapped_by_exact_identity_and_finite_value_checks(tmp_path, case):
    m = module()
    clock = Clock()
    def change(request, body, values):
        if request.kind != "chain":
            return body
        value = json.loads(body)
        row = value["calls"][0]
        if case == "wrong_root":
            row["instrument"]["symbol"] = "IWM261113C00500000"
        elif case == "wrong_expiry":
            row["instrument"]["symbol"] = request.symbol + "261120C00500000"
        elif case == "trailing_osi":
            row["instrument"]["symbol"] += "garbage"
        elif case == "boolean_greek":
            row["optionDetails"]["greeks"]["delta"] = True
        else:
            row["bid"] = "NaN" if case == "nan" else "Infinity"
        return json.dumps(value).encode()
    with ResearchStore(tmp_path / "research", m.build_plan(["2026-11-13"])) as store:
        transport = Transport(m, store, clock, change)
        result = await make(m, store, transport, clock).capture_cycle("cycle-1")
        assert result["has_gaps"] is True
        for row in store.attempts("cycle-1"):
            if row["request"]["kind"] == "chain":
                assert row["body"]
                assert row["parsed"]["errors"] == 1
                assert store.observations(row["attempt_id"]) == []


@pytest.mark.asyncio
async def test_budget_refusal_never_dispatches_or_returns_a_peer_slot(tmp_path):
    m = module()
    budget, clock = Budget(max_inflight=1), Clock()
    await budget.acquire_n(1, "api.public.com", now=clock.mono)
    try:
        with ResearchStore(tmp_path / "research", m.build_plan(["2026-11-13"])) as store:
            transport = Transport(m, store, clock)
            result = await make(m, store, transport, clock, budget).capture_cycle("cycle-1")
            assert result["status"] == "stopped"
            assert transport.calls == []
            assert budget.status(now=clock.mono)["inflight"] == 1
            assert budget.status(now=clock.mono)["available"] == 19
            assert budget.releases == 0
            assert store.attempts("cycle-1")[0]["status"] == "budget_refused"
    finally:
        budget.release()


@pytest.mark.asyncio
async def test_peer_429_during_success_is_not_cleared_by_completion_and_no_retry_occurs(tmp_path):
    m = module()
    budget, clock = Budget(), Clock()
    await budget.acquire_n(1, "api.public.com", now=clock.mono)
    def throttle(request, body, values):
        clock.advance(1)
        budget.record_429("api.public.com", now=clock.mono, retry_after=60)
    try:
        with ResearchStore(tmp_path / "research", m.build_plan(["2026-11-13"])) as store:
            transport = Transport(m, store, clock, throttle)
            result = await make(m, store, transport, clock, budget).capture_cycle("cycle-1")
            assert len(transport.calls) == 1
            assert result["status"] == "stopped"
            assert budget.status(now=clock.mono)["inflight"] == 1
            assert "api.public.com" in budget.status(now=clock.mono)["cooldowns"]
            assert budget.status(now=clock.mono)["available"] == 18
            assert budget.releases == 1
    finally:
        budget.release()


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["closed", "paused", "after_pace_close", "attempt_cap", "read_cap"])
async def test_admission_checks_before_every_dispatch_are_finite_and_fail_closed(tmp_path, case):
    m = module()
    clock = Clock(datetime(2026, 11, 6, 20, 59, 59, tzinfo=UTC) if case == "after_pace_close" else AT)
    limits = m.Limits(max_attempts=2) if case == "attempt_cap" else m.Limits()
    if case == "read_cap":
        limits = m.Limits(max_total_read_bytes=1114112)
    with ResearchStore(tmp_path / "research", m.build_plan(["2026-11-13"], limits)) as store:
        transport = Transport(m, store, clock)
        gate = (lambda now: False) if case == "closed" else None
        if case == "after_pace_close":
            from services.solstice_capture_policy import capture_market_hours
            gate = capture_market_hours
        result = await make(m, store, transport, clock, gate=gate,
                            pacer=Pacer(lambda: clock.advance(2)) if case == "after_pace_close" else None,
                            stop=(lambda: True) if case == "paused" else None).capture_cycle("cycle-1")
        expected = 2 if case == "attempt_cap" else 1 if case == "read_cap" else 0
        assert len(transport.calls) == expected
        assert result["status"] in {"skipped", "stopped"}
        assert store.status()["reserved_attempts"] <= 2 if case == "attempt_cap" else True


@pytest.mark.asyncio
async def test_timeout_keeps_slot_and_store_until_uncooperative_transport_settles(tmp_path):
    m = module()
    clock, budget = Clock(), Budget()
    await budget.acquire_n(1, "api.public.com", now=clock.mono)
    release, closed = asyncio.Event(), asyncio.Event()
    @asynccontextmanager
    async def opening(request, attempt_id):
        try:
            try:
                await release.wait()
            except asyncio.CancelledError:
                await release.wait()
            async def chunks():
                yield body_for(request)
            yield m.RawReply(http_status=200, chunks=chunks())
        finally:
            closed.set()
    store = ResearchStore(tmp_path / "research", m.build_plan(["2026-11-13"], m.Limits(request_timeout_s=0.03)))
    try:
        collector = make(m, store, type("T", (), {"open": staticmethod(opening)})(), clock, budget)
        result = await asyncio.wait_for(collector.capture_cycle("cycle-1"), 0.3)
        assert result["status"] == "stopped"
        assert budget.status(now=clock.mono)["inflight"] == 2
        assert budget.releases == 0
        assert store.close() is False
        with pytest.raises(ResearchRefusal, match="writer_held"):
            ResearchStore(tmp_path / "research", m.build_plan(["2026-11-13"], m.Limits(request_timeout_s=0.03)))
        release.set()
        await asyncio.wait_for(closed.wait(), 1)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert budget.status(now=clock.mono)["inflight"] == 1
        assert budget.releases == 1 and store.closed is True
        with ResearchStore(tmp_path / "research", m.build_plan(["2026-11-13"], m.Limits(request_timeout_s=0.03))) as reopened:
            assert reopened.attempts("cycle-1")[0]["body"] is None
            assert reopened.status()["reserved_attempts"] == 1
    finally:
        release.set()
        await asyncio.sleep(0)
        store.close()
        budget.release()


@pytest.mark.asyncio
async def test_cancelled_capture_propagates_and_cleans_only_its_slot(tmp_path):
    m = module()
    clock, budget = Clock(), Budget()
    await budget.acquire_n(1, "api.public.com", now=clock.mono)
    entered = asyncio.Event()
    @asynccontextmanager
    async def opening(request, attempt_id):
        entered.set()
        await asyncio.Event().wait()
        yield
    try:
        with ResearchStore(tmp_path / "research", m.build_plan(["2026-11-13"])) as store:
            collector = make(m, store, type("T", (), {"open": staticmethod(opening)})(), clock, budget)
            task = asyncio.create_task(collector.capture_cycle("cycle-1"))
            await entered.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert budget.status(now=clock.mono)["inflight"] == 1
            assert budget.status(now=clock.mono)["available"] == 18
            assert budget.releases == 1
            assert store.attempts("cycle-1")[0]["status"] == "cancelled"
    finally:
        budget.release()


@pytest.mark.asyncio
async def test_expired_cooldown_does_not_permanently_block_a_new_attempt(tmp_path):
    m, clock, budget = module(), Clock(), Budget()
    budget.record_429("api.public.com", now=clock.mono - 2, retry_after=1)
    with ResearchStore(tmp_path / "research", m.build_plan(["2026-11-13"])) as store:
        transport = Transport(m, store, clock)
        result = await make(m, store, transport, clock, budget).capture_cycle("cycle-1")
        assert result["status"] == "committed"
        assert len(transport.calls) == 6


@pytest.mark.asyncio
async def test_subsecond_peer_cooldown_after_admission_still_prevents_dispatch(tmp_path):
    m, clock = module(), Clock()
    class PeerBudget(Budget):
        async def acquire_n(self, *args, **kwargs):
            await super().acquire_n(*args, **kwargs)
            self.record_429("api.public.com", now=clock.mono - 0.5, retry_after=1)
    budget = PeerBudget()
    with ResearchStore(tmp_path / "research", m.build_plan(["2026-11-13"])) as store:
        transport = Transport(m, store, clock)
        result = await make(m, store, transport, clock, budget).capture_cycle("cycle-1")
        assert result["dispatch_attempts"] == 0 and transport.calls == []
        assert budget.releases == 1 and budget.status(now=clock.mono)["available"] == 19


@pytest.mark.asyncio
async def test_gate_closure_after_one_response_is_stopped_not_zero_request_skipped(tmp_path):
    m, clock = module(), Clock()
    with ResearchStore(tmp_path / "research", m.build_plan(["2026-11-13"])) as store:
        transport = Transport(m, store, clock, lambda *args: clock.advance(1))
        result = await make(m, store, transport, clock, gate=lambda now: now == AT).capture_cycle("cycle-1")
        assert result["dispatch_attempts"] == 1 and len(transport.calls) == 1
        assert result["status"] == "stopped"


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [b'{"access\\u0054oken":"synthetic-withhold"}',
                                  b'{"accountId":"synthetic-withhold"}',
                                  b'{"x-api-key":"synthetic-withhold"}'])
async def test_sensitive_field_spellings_are_withheld_before_any_raw_commit(tmp_path, body):
    m, clock = module(), Clock()
    with ResearchStore(tmp_path / "research", m.build_plan(["2026-11-13"])) as store:
        transport = Transport(m, store, clock, lambda *args: body)
        result = await make(m, store, transport, clock).capture_cycle("cycle-1")
        assert result["has_gaps"] is True
        for row in store.attempts("cycle-1"):
            assert row["body"] == b""
            assert row["response"]["withholding_reason"] == "sensitive_body"
        assert b"synthetic-withhold" not in (store.directory / "collector.sqlite3").read_bytes()


@pytest.mark.asyncio
async def test_cycle_deadline_includes_waiting_for_shared_pacer(tmp_path):
    m, clock, budget = module(), Clock(), Budget()
    class WaitingPacer:
        async def wait(self):
            await asyncio.Event().wait()
    with ResearchStore(tmp_path / "research", m.build_plan(["2026-11-13"], m.Limits(cycle_timeout_s=0.03))) as store:
        transport = Transport(m, store, clock)
        result = await asyncio.wait_for(make(m, store, transport, clock, budget, pacer=WaitingPacer()).capture_cycle("cycle-1"), 0.3)
        assert result["status"] == "stopped" and result["reason"] == "cycle_deadline"
        assert transport.calls == [] and budget.releases == 0


@pytest.mark.asyncio
async def test_cancellation_at_budget_admission_return_still_owns_exactly_one_slot(tmp_path):
    m, clock = module(), Clock()
    capture = None
    class CancelAfterAdmission(Budget):
        async def acquire_n(self, *args, **kwargs):
            await super().acquire_n(*args, **kwargs)
            capture.cancel()
    budget = CancelAfterAdmission()
    with ResearchStore(tmp_path / "research", m.build_plan(["2026-11-13"])) as store:
        transport = Transport(m, store, clock)
        capture = asyncio.create_task(make(m, store, transport, clock, budget).capture_cycle("cycle-1"))
        with pytest.raises(asyncio.CancelledError):
            await capture
        assert transport.calls == [] and budget.status(now=clock.mono)["inflight"] == 0
        assert budget.releases == 1 and budget.status(now=clock.mono)["available"] == 19


@pytest.mark.asyncio
async def test_response_close_must_settle_before_slot_release_and_late_body_is_discarded(tmp_path):
    m, clock, budget = module(), Clock(), Budget()
    release, closing = asyncio.Event(), asyncio.Event()
    @asynccontextmanager
    async def opening(request, attempt_id):
        async def chunks():
            yield body_for(request)
        try:
            yield m.RawReply(chunks())
        finally:
            closing.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                await release.wait()
    with ResearchStore(tmp_path / "research", m.build_plan(["2026-11-13"], m.Limits(request_timeout_s=0.03))) as store:
        collector = make(m, store, type("T", (), {"open": staticmethod(opening)})(), clock, budget)
        try:
            result = await asyncio.wait_for(collector.capture_cycle("cycle-1"), 0.3)
            assert closing.is_set() and result["reason"] == "request_timeout"
            assert budget.releases == 0 and budget.status(now=clock.mono)["inflight"] == 1
            assert store.attempts("cycle-1")[0]["body"] is None
            assert (await collector.capture_cycle("cycle-2"))["reason"] == "collector_busy_or_quarantined"
        finally:
            release.set()
            await asyncio.sleep(0)
            await asyncio.sleep(0)
        assert budget.releases == 1 and store.attempts("cycle-1")[0]["body"] is None


@pytest.mark.asyncio
async def test_parsed_commit_failure_keeps_previously_committed_exact_raw(tmp_path):
    m, clock = module(), Clock()
    with ResearchStore(tmp_path / "research", m.build_plan(["2026-11-13"])) as store:
        def fail(*args):
            raise ResearchRefusal("store_commit_failed")
        store.record_parsed = fail
        transport = Transport(m, store, clock)
        result = await make(m, store, transport, clock).capture_cycle("cycle-1")
        assert result["status"] == "failed" and len(transport.calls) == 1
        row = store.attempts("cycle-1")[0]
        assert row["status"] == "raw_committed" and row["parsed"] is None
        assert row["body"] == body_for(transport.calls[0])


@pytest.mark.asyncio
async def test_empty_cache_and_backward_wall_clock_keep_honest_gap_markers(tmp_path):
    m, clock = module(), Clock()
    def change(request, body, values):
        values["source_delivery"] = "cache"
        clock.wall -= timedelta(seconds=1)
        return b'{"quotes":[]}'
    with ResearchStore(tmp_path / "research", m.build_plan(["2026-11-13"])) as store:
        transport = Transport(m, store, clock, change)
        result = await make(m, store, transport, clock).capture_cycle("cycle-1")
        assert result["status"] == "stopped" and result["has_gaps"] is True
        row = store.attempts("cycle-1")[0]
        assert row["response"]["wall_clock_regressed"] is True
        assert row["response"]["source_delivery"] == "cache"
        assert row["parsed"]["status"] == "empty" and store.observations(row["attempt_id"]) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["429", "open_error", "stream_error", "chunk_violation"])
async def test_transport_failures_stop_or_preserve_incomplete_evidence_without_retry(tmp_path, case):
    m, clock, budget = module(), Clock(), Budget()
    calls = 0
    @asynccontextmanager
    async def opening(request, attempt_id):
        nonlocal calls
        calls += 1
        if case == "open_error":
            raise RuntimeError("synthetic-secret-must-not-be-logged")
        async def chunks():
            if case == "stream_error":
                yield b'{"quotes":'
                raise RuntimeError("synthetic-secret-must-not-be-logged")
            yield b"x" * 65537 if case == "chunk_violation" else body_for(request)
        yield m.RawReply(chunks(), http_status=429 if case == "429" else 200, retry_after="17")
    with ResearchStore(tmp_path / "research", m.build_plan(["2026-11-13"])) as store:
        result = await make(m, store, type("T", (), {"open": staticmethod(opening)})(), clock, budget).capture_cycle("cycle-1")
        assert result["has_gaps"] is True
        assert calls == result["dispatch_attempts"] <= 6
        assert budget.releases == calls and budget.status(now=clock.mono)["inflight"] == 0
        assert budget.status(now=clock.mono)["available"] == 20 - calls
        if case != "stream_error":
            assert calls == 1 and result["status"] == "stopped"
        if case == "429":
            assert budget.status(now=clock.mono)["cooldowns"]["api.public.com"] == 17
        if case in {"stream_error", "chunk_violation"}:
            row = store.attempts("cycle-1")[0]
            assert row["body"] == b"" and row["response"]["body_complete"] is False
            assert row["response"]["source_body_sha256"] is None
        assert "synthetic-secret" not in json.dumps(result)
        assert b"synthetic-secret" not in (store.directory / "collector.sqlite3").read_bytes()


@pytest.mark.parametrize("value", ["orders", "portfolio", "auth", "accounts", "http://elsewhere"])
def test_request_kind_cannot_expand_to_nonmarket_routes(value):
    m = module()
    with pytest.raises(ResearchRefusal):
        m.RequestSpec(value, "SPY", None)


def test_plan_freezes_explicit_parser_version_with_scope_and_limits():
    plan = module().build_plan(["2026-11-13"])
    assert plan["parser_id"] == "public-option-contract+strict-research.v1"


def test_offline_cli_preview_has_no_capture_flag_or_store_side_effect(tmp_path):
    module()
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts" / "collect_public_research.py"
    command = ["/Users/nav/.local/share/floww-free-test312/bin/python", "-I", "-B", str(script), "--expiry", "2026-11-13"]
    result = subprocess.run(command, capture_output=True, text=True, cwd=tmp_path, timeout=5)
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert value["status"] == "prepared"
    assert value["live_transport"] == "absent"
    assert value["manifest"]["symbols"] == ["SPY", "QQQ"]
    assert value["provider_attempts"] == 0 and list(tmp_path.iterdir()) == []
    rejected = subprocess.run(command + ["--start"], capture_output=True, text=True, cwd=tmp_path, timeout=5)
    assert rejected.returncode != 0 and list(tmp_path.iterdir()) == []

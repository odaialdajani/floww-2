"""Exact deterministic critical recipes; no real model or provider calls.

The32 functional comparison cases are never executed here.
"""
import asyncio
import copy
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from mongomock_motor import AsyncMongoMockClient

from scripts.research_comparison_inputs import synthetic_chain
from scripts.research_comparison_transport import exercise, local_server
from scripts.research_eval_metrics import CaseTrace, MeasuredModel, observe_progress_stream
from services.agent.codex_model import OAuthUsage
from services.agent.contracts import request_spec, validate_model_answer
from services.agent.local_access import COOKIE
from services.agent.reads import ResearchReads
from services.agent.repository import AgentRepository
from services.agent.research import ResearchService

ROOT = Path(__file__).resolve().parents[3]
PROPOSAL = ROOT / '.planning/eval/research-fresh-comparison-proposal-20260926-v3.json'
CASES = {c['id']: c for c in json.loads(PROPOSAL.read_bytes())['critical_cases']}


def item(case_id):
    case = CASES[case_id]
    return {'id': case_id, 'body': copy.deepcopy(case['body']), 'clock': copy.deepcopy(case['clock']),
            'chains': {t: synthetic_chain(t, {}) for t in case['tickers']},
            'maps': {}, 'history': {}, 'alerts': {'mode': 'controlled_empty_alerts', 'parameters': {}}}


def identity():
    return f'{int(time.time()*1000)}-{uuid.uuid4()}'


async def repository():
    repo = AgentRepository(AsyncMongoMockClient(tz_aware=True).critical)
    await repo.initialize()
    return repo


async def until(predicate):
    async with asyncio.timeout(3):
        while not predicate():
            await asyncio.sleep(.002)


class ForbiddenModel:
    single_attempt = True
    async def once(self, *args, **kwargs):
        raise AssertionError('Critical recipe attempted unexpected model work')


@pytest.fixture(autouse=True)
def block_external_connections(monkeypatch):
    import socket
    def guarded(original):
        def call(sock, address):
            if not isinstance(address, tuple) or address[0] not in {'127.0.0.1', '::1'}:
                raise AssertionError('Critical recipe attempted external network')
            return original(sock, address)
        return call
    monkeypatch.setattr(socket.socket, 'connect', guarded(socket.socket.connect))
    monkeypatch.setattr(socket.socket, 'connect_ex', guarded(socket.socket.connect_ex))


@pytest.mark.asyncio
async def test_critical_missing_price():
    case = item('critical_missing_price')
    case['chains'] = {}
    report = await exercise(case, await repository(), model_factory=lambda _: ForbiddenModel())
    assert report['errors'] == [] and report['saved_reopen_identical']
    answer = report['saved_turn']['answer']
    assert not any(f['metric'] == 'Underlying price' for f in answer['facts'])
    assert 'unavailable' in answer['summary']
    assert report['trace']['model_invocations'] == 0
    assert report['read_metrics']['started'] == 1
    assert report['read_entry_evidence']['source_callbacks'] == [{'kind': 'context', 'ticker': 'TLT'}]


@pytest.mark.asyncio
@pytest.mark.parametrize('case_id', ['critical_four_tickers', 'critical_conflicting_expiries', 'critical_exclusion_only'])
async def test_critical_refusal(case_id):
    report = await exercise(item(case_id), await repository(), expected_status=422,
                            model_factory=lambda _: ForbiddenModel())
    assert report['errors'] == [] and report['owned_turn_count'] == 0
    assert report['read_entry_evidence'] == {'snapshot_entries': [], 'source_callbacks': [],
        'scope': 'Actual snapshot/source callback entries; calculation entries remain in the saved capability ledger'}
    assert report['trace']['model_invocations'] == 0


@pytest.mark.asyncio
async def test_critical_nonfinite_input():
    case = item('critical_nonfinite_input')
    case['chains']['IWM']['spot'] = float('nan')
    report = await exercise(case, await repository(), model_factory=lambda _: ForbiddenModel())
    assert report['saved_turn']['status'] == 'failed'
    assert report['saved_turn']['answer'] is None
    assert report['saved_reopen_identical']
    assert report['read_metrics']['started'] == 2
    assert report['read_metrics']['reserved'] == 2
    assert report['trace']['model_invocations'] == 0
    assert report['read_entry_evidence']['source_callbacks'] == [
        {'kind': 'context', 'ticker': 'IWM'}, {'kind': 'flow', 'ticker': 'IWM'}]


@pytest.mark.asyncio
@pytest.mark.parametrize('case_id,reason', [
    ('critical_unknown_reference', 'Unknown evidence'),
    ('critical_wrong_comparison', 'Incompatible comparison scope'),
    ('critical_free_text_claim', 'Unrestricted factual commentary'),
])
async def test_critical_invalid_interpretation(case_id, reason, record_property):
    captured = {}
    class InvalidModel:
        single_attempt = True
        async def once(self, question, facts, turn_id, **kwargs):
            captured['facts'] = copy.deepcopy(facts)
            refs = [f['id'] for f in facts[:2]]
            answer = {'sections': [{'name': 'Structure', 'fact_ids': refs, 'interpretation': 'limited'}],
                      'relationships': []}
            if case_id == 'critical_unknown_reference':
                answer['sections'][0]['fact_ids'] = ['nonexistent-critical-reference']
            elif case_id == 'critical_free_text_claim':
                answer['sections'][0]['commentary'] = '<script>guaranteed bullish price999999</script>'
            else:
                left = next(f for f in facts if f['metric'] == 'Underlying price')
                right = next(f for f in facts if f['unit'] != left['unit'] and isinstance(f['value'], (int, float)))
                refs[:] = [left['id'], right['id']]
                answer['relationships'] = [{'kind': 'above', 'fact_id': left['id'], 'other_fact_id': right['id']}]
            captured['answer'] = answer
            return {'status': 'ok', 'name': 'research_answer', 'data': answer}
    result = await exercise(item(case_id), await repository(), model_factory=lambda _: InvalidModel())
    assert result['errors'] == [] and result['saved_reopen_identical']
    record_property('fixture_model_entries', result['trace']['model_invocations'])
    assert result['trace']['model_invocations'] == 1
    assert result['trace']['managed_turn_start_attempts'] == 0
    answer = result['saved_turn']['answer']
    assert answer['mode'] == 'deterministic' and 'not supported' in answer['model_status']
    assert answer['facts'] == captured['facts']
    assert 'guaranteed bullish price999999' not in json.dumps(answer)
    assert not answer.get('model_relationships') and not answer.get('model_sections')
    with pytest.raises(ValueError, match=reason):
        validate_model_answer(captured['answer'], {f['id']: f for f in captured['facts']})


async def admitted(client, case_id, request_id=None):
    response = await client.post('/api/agent/session')
    response.raise_for_status()
    body = copy.deepcopy(CASES[case_id]['body'])
    body['request_id'] = request_id or identity()
    response = await client.post('/api/agent/ask', json=body)
    response.raise_for_status()
    return response.json()['turn_id'], body


@pytest.mark.asyncio
async def test_critical_other_owner_stop():
    repo = await repository()
    entered, release = threading.Event(), threading.Event()
    calls = []
    def context(*args):
        calls.append('context')
        entered.set()
        release.wait(4)
        return {'spot': 100, 'contracts': []}
    service = ResearchService(repo, ResearchReads(context, lambda *a: None, lambda *a: []))
    try:
        async with local_server(service) as base:
            async with httpx.AsyncClient(base_url=base, headers={'Origin': base}, trust_env=False) as alice:
                turn_id, _ = await admitted(alice, 'critical_other_owner_stop')
                await until(entered.is_set)
                budget = service._read_budgets[turn_id]
                before = budget.closed
                async with httpx.AsyncClient(base_url=base, headers={'Origin': base}, trust_env=False) as bob:
                    (await bob.post('/api/agent/session')).raise_for_status()
                    for method, route in [('POST', 'cancel'), ('GET', 'turn'), ('GET', 'stream')]:
                        response = await bob.request(method, f'/api/agent/{route}/{turn_id}')
                        assert response.status_code == 404
                        assert 'answer' not in response.json() and 'read_activity' not in response.json()
                assert budget.closed == before is False
                release.set()
                await observe_progress_stream(alice, turn_id, CaseTrace())
                saved = (await alice.get('/api/agent/turn/' + turn_id)).json()
                assert saved['status'] == 'completed' and saved['answer'] is not None
                assert calls == ['context']
    finally:
        release.set()


@pytest.mark.asyncio
async def test_critical_last_allowance_race(record_property):
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27017', serverSelectionTimeoutMS=3000, tz_aware=True)
    try:
        server = await client.admin.command('buildInfo')
        record_property('real_storage_version', server['version'])
        database = client['research_critical_race_' + uuid.uuid4().hex]
        assert not await database.list_collection_names()
        usage = OAuthUsage(database.usage, daily_limit=1)
        turns = [str(uuid.uuid4()) for _ in range(2)]
        won = await asyncio.gather(*(usage.reserve('critical-owner-' + str(i), turn, {'model': 'FIXTURE_ONLY'})
                                    for i, turn in enumerate(turns)))
        assert sum(x is not None for x in won) == 1
        winner = next(x for x in won if x is not None)
        await usage.finish(winner, status='uncertain', fixture_boundary='entered_then_interrupted')
        assert (await usage.state())['calls'] == 1
        row = await database.usage.find_one({'_id': winner[0]})
        assert row['entries'][winner[1]]['status'] == 'uncertain'
        assert row['entries'][winner[1]]['actual_cost'] is None
        assert all(v is None for v in await asyncio.gather(*(usage.reserve('critical-owner-' + str(i), turn, {})
                                                            for i, turn in enumerate(turns))))
        assert (await usage.state())['calls'] == 1
    finally:
        client.close()


@pytest.mark.asyncio
async def test_critical_same_identity_replay():
    repo = await repository()
    calls = []
    def context(*args):
        calls.append('context')
        return {'spot': 100, 'contracts': []}
    trace = CaseTrace()
    service = ResearchService(repo, ResearchReads(context, lambda *a: None, lambda *a: []))
    async with local_server(service) as base:
        async with httpx.AsyncClient(base_url=base, headers={'Origin': base}, trust_env=False) as client:
            turn_id, body = await admitted(client, 'critical_same_identity_replay')
            await observe_progress_stream(client, turn_id, trace)
            original = (await client.get('/api/agent/turn/' + turn_id)).json()
            original_calls = list(calls)
            replay = await client.post('/api/agent/ask', json=body)
            assert replay.status_code == 200 and replay.json()['turn_id'] == turn_id
            await observe_progress_stream(client, turn_id, trace)
            assert (await client.get('/api/agent/turn/' + turn_id)).json() == original
            assert calls == original_calls and not service.tasks and not service._read_budgets
            changed = {**body, 'question': 'A different saved question for DIA'}
            assert (await client.post('/api/agent/ask', json=changed)).status_code == 409
            async with httpx.AsyncClient(base_url=base, headers={'Origin': base}, trust_env=False) as stranger:
                (await stranger.post('/api/agent/session')).raise_for_status()
                assert (await stranger.get('/api/agent/turn/' + turn_id)).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize('variant', ['cancel', 'deadline', 'prestart', 'queued_expiry'])
async def test_critical_cancel_late_worker(variant):
    repo = await repository()
    entered, release, exited = threading.Event(), threading.Event(), threading.Event()
    calls = []
    def context(*args):
        calls.append('context')
        return {'spot': 100, 'contracts': []}
    def alerts(*args):
        calls.append('alerts')
        entered.set()
        release.wait(4)
        exited.set()
        return []
    trace = CaseTrace()
    timeout = .12 if variant in {'deadline', 'queued_expiry'} else 3
    service = ResearchService(repo, ResearchReads(context, lambda *a: None, alerts),
                              model=MeasuredModel(ForbiddenModel(), trace), timeout=timeout, concurrent=1)
    spec = request_spec(CASES['critical_cancel_late_worker']['body'])
    held_slot = variant == 'queued_expiry'
    if held_slot:
        await service._slots.acquire()
    try:
        turn = await service.ask('critical-owner', identity(), spec)
        key = turn['turn_id']
        if variant == 'prestart':
            await service.cancel('critical-owner', key)
        elif variant == 'cancel':
            await until(entered.is_set)
            await service.cancel('critical-owner', key)
        await asyncio.gather(*list(service.tasks.values()), return_exceptions=True)
        await asyncio.sleep(0)
        saved = await repo.read('critical-owner', key)
        assert saved['status'] == ('cancelled' if variant in {'cancel', 'prestart'} else 'failed')
        assert saved['answer'] is None
        activity = copy.deepcopy(saved['read_activity'])
        if variant in {'prestart', 'queued_expiry'}:
            assert activity['started'] == activity['reserved'] == 0
            assert calls == [] and activity['closed'] and activity['entry_count_complete']
        else:
            assert calls == ['context', 'alerts']
            assert activity['started'] == activity['reserved'] == 2
            assert activity['attempts'][-1]['worker_unresolved'] is True
            release.set()
            await until(exited.is_set)
        assert not service.tasks and not service._read_budgets
        assert trace.snapshot()['model_invocations'] == 0
        assert await repo.read('critical-owner', key) == saved
        assert (await repo.read('critical-owner', key))['read_activity'] == activity
    finally:
        release.set()
        if held_slot:
            service._slots.release()
        await service.close()


@pytest.mark.asyncio
async def test_critical_stream_display_boundary():
    repo = await repository()
    calls = []
    def context(*args):
        calls.append('context')
        time.sleep(.20)
        return {'spot': 100}
    trace = CaseTrace()
    service = ResearchService(repo, ResearchReads(context, lambda *a: None, lambda *a: []),
                              model=MeasuredModel(ForbiddenModel(), trace))
    async with local_server(service) as base:
        async with httpx.AsyncClient(base_url=base, headers={'Origin': base}, trust_env=False) as client:
            turn_id, _ = await admitted(client, 'critical_stream_display_boundary')
            await observe_progress_stream(client, turn_id, trace)
            first_marks = dict(trace.marks)
            assert first_marks['first_stream_progress_received'] < first_marks['terminal_stream_received']
            await observe_progress_stream(client, turn_id, trace)
            assert trace.marks == first_marks
            one = (await client.get('/api/agent/turn/' + turn_id)).json()
            two = (await client.get('/api/agent/turn/' + turn_id)).json()
            assert one == two and one['status'] == 'completed'
            assert one['read_activity']['started'] == 1 and calls == ['context']
    from fastapi import FastAPI
    async with httpx.AsyncClient(base_url='http://test', transport=httpx.ASGITransport(FastAPI())) as buffered:
        with pytest.raises(ValueError, match='real HTTP'):
            await observe_progress_stream(buffered, turn_id, trace)
    assert trace.snapshot()['first_browser_display_s'] is None
    assert trace.snapshot()['model_invocations'] == 0


@pytest.mark.asyncio
async def test_critical_crash_unknown_dispatch(record_property):
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27017', serverSelectionTimeoutMS=3000, tz_aware=True)
    try:
        server = await client.admin.command('buildInfo')
        record_property('real_storage_version', server['version'])
        for boundary in ('reserved_before_dispatch', 'local_dispatch_signal'):
            name = 'research_critical_crash_' + uuid.uuid4().hex
            database = client[name]
            assert not await database.list_collection_names()
            process = await asyncio.to_thread(subprocess.run, [sys.executable, '-m',
                'scripts.verify_research_comparison_critical', '--crash-child', name, '--boundary', boundary],
                cwd=ROOT / 'backend', capture_output=True, timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            record_property(boundary + '_child_exit_code', process.returncode)
            assert process.returncode == 73, process.stderr.decode(errors='replace')
            probe = await database.critical_probe.find_one({'_id': 'controlled-crash'})
            assert probe and probe['boundary'] == boundary
            repo = AgentRepository(database)
            await repo.initialize()
            saved = await repo.read(probe['owner'], probe['turn_id'])
            assert saved['status'] == 'interrupted' and saved['answer'] is None
            usage = OAuthUsage(database.usage)
            assert (await usage.state())['calls'] == 1
            day = await database.usage.find_one({'_id': probe['reservation'][0]})
            entry = day['entries'][probe['reservation'][1]]
            assert entry['status'] == 'uncertain' and entry['actual_cost'] is None
            assert await usage.reserve(probe['owner'], probe['turn_id'], {'model': 'FIXTURE_ONLY'}) is None
            reads = []
            service = ResearchService(repo, ResearchReads(lambda *a, target=reads: target.append('unexpected'),
                                      lambda *a: None, lambda *a: []), model=ForbiddenModel())
            try:
                replay = await service.ask(probe['owner'], probe['request_id'], probe['spec'])
                assert replay['status'] == 'interrupted'
                assert not service.tasks and not service._read_budgets and reads == []
                assert (await usage.state())['calls'] == 1
                assert await database.dispatch_signals.count_documents({}) == (boundary == 'local_dispatch_signal')
            finally:
                await service.close()
    finally:
        client.close()

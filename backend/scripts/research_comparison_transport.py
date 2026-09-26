"""Measured real HTTP research execution for an isolated comparison process.

This building block does not authorize model calls or select candidates. Callers
must bind/verify inputs and shared budgets before providing any model factory.
Tests use development-only questions; frozen comparison cases are not run here.
"""
from __future__ import annotations

import asyncio
import copy
import os
import socket
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import patch

import httpx
import uvicorn
from fastapi import FastAPI

from routes.agent import router
from scripts.research_comparison_alerts import AlertFixture
from scripts.research_comparison_history import seed_history
from scripts.research_eval_metrics import (
    CaseTrace,
    MeasuredModel,
    observe_progress_stream,
    read_metrics,
    saved_progress_metrics,
)
from services.agent.local_access import COOKIE
from services.agent.reads import ResearchReads
from services.agent.research import ResearchService

_CLEANUP_SECONDS = 5


class FixtureReads(ResearchReads):
    def __init__(self, item, alerts):
        self.item = copy.deepcopy(item)
        self.snapshot_entries = []
        self.source_callbacks = []
        def read_chain(ticker, _):
            self.source_callbacks.append({'kind': 'context', 'ticker': ticker})
            return copy.deepcopy(self.item['chains'].get(ticker))
        def read_map(ticker, _):
            self.source_callbacks.append({'kind': 'map', 'ticker': ticker})
            return copy.deepcopy(self.item['maps'].get(ticker))
        def read_alerts(ticker):
            self.source_callbacks.append({'kind': 'flow', 'ticker': ticker})
            return alerts.read(ticker)
        super().__init__(read_chain, read_map, read_alerts)

    async def snapshot(self, *args, **kwargs):
        self.snapshot_entries.append({'ticker': args[0] if args else kwargs.get('ticker')})
        kwargs['now'] = datetime.fromisoformat(self.item['clock']['at'].replace('Z', '+00:00'))
        return await super().snapshot(*args, **kwargs)


async def _stop_owned(closing, server, worker):
    failure = None
    done, _ = await asyncio.wait({closing}, timeout=_CLEANUP_SECONDS)
    if not done:
        closing.cancel()
        settled, _ = await asyncio.wait({closing}, timeout=_CLEANUP_SECONDS)
        failure = RuntimeError('Owned service cleanup timed out; discard evaluation process')
        if not settled:
            failure = RuntimeError('Owned service cleanup ignored cancellation; discard evaluation process')
    if closing.done():
        if closing.cancelled():
            failure = failure or asyncio.CancelledError()
        else:
            failure = closing.exception() or failure
    done, _ = await asyncio.wait({worker}, timeout=_CLEANUP_SECONDS)
    if not done:
        server.force_exit = True
        worker.cancel()
        settled, _ = await asyncio.wait({worker}, timeout=_CLEANUP_SECONDS)
        failure = RuntimeError('Owned listener cleanup timed out; discard evaluation process')
        if not settled:
            failure = RuntimeError('Owned listener ignored cancellation; discard evaluation process')
    if worker.done() and not worker.cancelled():
        failure = worker.exception() or failure
    return failure


@asynccontextmanager
async def local_server(service):
    """Own only this listener/service; never starts market workers or full app."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    worker = None
    server = None
    try:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
        sock.listen(16)
        sock.setblocking(False)
        base = f'http://127.0.0.1:{port}'
        with patch.dict(os.environ, {'FLOWW_AGENT_DEPLOYMENT': 'local', 'FLOWW_AGENT_ORIGINS': base}):
            app = FastAPI()
            app.include_router(router)
            app.state.research_service = service
            server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port,
                log_level='error', proxy_headers=False, lifespan='off'))
            worker = asyncio.create_task(server.serve(sockets=[sock]))
            try:
                async with asyncio.timeout(5):
                    while not server.started:
                        if worker.done():
                            await worker
                            raise RuntimeError('Owned research listener stopped before startup')
                        await asyncio.sleep(.005)
                yield base
            finally:
                server.should_exit = True
                closing = asyncio.create_task(service.close())
                cleanup = asyncio.create_task(_stop_owned(closing, server, worker))
                interruption = None
                # Shield the complete bounded cleanup, including listener exit.
                # Repeated caller cancellations cannot abandon its owned tasks.
                while not cleanup.done():
                    try:
                        await asyncio.shield(cleanup)
                    except asyncio.CancelledError as exc:
                        interruption = exc
                        closing.cancel()
                failure = cleanup.result()
                if failure is not None:
                    raise failure
                if interruption is not None:
                    raise interruption
    finally:
        sock.close()


async def exercise(item, repository, *, expected_status=200, model_factory=None, trace_sink=None):
    """One fresh owner/case. No source refresh, fallback store, or implicit model."""
    if expected_status not in {200, 422}:
        raise ValueError('Comparison supports admitted or pre-admission refusal cases')
    with AlertFixture(item) as alerts:
        reads = FixtureReads(item, alerts)
        service = ResearchService(repository, reads)
        async with local_server(service) as base:
            async with httpx.AsyncClient(base_url=base, headers={'Origin': base}, trust_env=False,
                                         timeout=135) as client:
                session = await client.post('/api/agent/session')
                if session.status_code != 200:
                    raise RuntimeError('Isolated owner admission failed')
                owner = await repository.owner(client.cookies.get(COOKIE))
                if not owner or await repository.turns.count_documents({'owner': owner}):
                    raise RuntimeError('Expected a new empty isolated owner')
                history_seed = await seed_history(repository, owner, item) if item.get('history') else []
                trace = CaseTrace(sink=trace_sink)
                if model_factory is not None:
                    service.model = MeasuredModel(model_factory(trace), trace)
                body = copy.deepcopy(item['body'])
                body['request_id'] = f'{int(time.time()*1000)}-{uuid.uuid4()}'
                trace.mark('request_started')
                admitted = await client.post('/api/agent/ask', json=body)
                trace.mark('admission_received')
                errors = []
                if admitted.status_code != expected_status:
                    errors.append('Actual admission differs from frozen expectation')
                result = {'id': item['id'], 'http_status': admitted.status_code, 'errors': errors,
                          'history_seed': history_seed,
                          'measurement_origin': 'After fixture/session setup, immediately before actual ask request',
                          'first_browser_display': 'unmeasured; HTTP progress receipt is not paint',
                          'model_authorization': 'Supplied by caller; this helper grants none'}
                if admitted.status_code != 200:
                    count = await repository.turns.count_documents({'owner': owner})
                    if count:
                        errors.append('Refused request unexpectedly saved work')
                    if reads.snapshot_entries or reads.source_callbacks or service.tasks:
                        errors.append('Refused request unexpectedly entered research reads')
                    result.update(refusal=admitted.json(), owned_turn_count=count)
                else:
                    turn_id = admitted.json()['turn_id']
                    terminal = await observe_progress_stream(client, turn_id, trace, timeout=130)
                    trace.mark('answer_lookup_started')
                    response = await client.get('/api/agent/turn/' + turn_id)
                    response.raise_for_status()
                    saved = response.json()
                    trace.mark('saved_answer_received')
                    repeat = await client.get('/api/agent/turn/' + turn_id)
                    repeat.raise_for_status()
                    identical = repeat.json() == saved
                    history_response = await client.get('/api/agent/history')
                    history_response.raise_for_status()
                    present = any(turn['turn_id'] == turn_id for turn in history_response.json().get('turns', []))
                    async with httpx.AsyncClient(base_url=base, headers={'Origin': base}, trust_env=False) as stranger:
                        stranger_session = await stranger.post('/api/agent/session')
                        stranger_session.raise_for_status()
                        foreign_status = (await stranger.get('/api/agent/turn/' + turn_id)).status_code
                    if not identical or not present or foreign_status != 404:
                        errors.append('Saved-answer reopen/history/privacy proof failed')
                    if saved.get('status') != 'completed' or terminal.get('status') != 'completed':
                        errors.append('Research did not complete successfully')
                    result.update(saved_turn=saved, saved_reopen_identical=identical,
                                  private_history_present=present, other_owner_status=foreign_status,
                                  read_metrics=read_metrics(saved), saved_progress=saved_progress_metrics(saved),
                                  owned_turn_count=await repository.turns.count_documents({'owner': owner}))
                trace.mark('verification_finished')
                trace.finish()
                result.update(trace=trace.snapshot(), alert_query_receipts=copy.deepcopy(alerts.receipts),
                              alert_population=copy.deepcopy(alerts.population),
                              read_entry_evidence={'snapshot_entries': copy.deepcopy(reads.snapshot_entries),
                                                   'source_callbacks': copy.deepcopy(reads.source_callbacks),
                                                   'scope': 'Actual snapshot/source callback entries; calculation entries remain in the saved capability ledger'})
                return result

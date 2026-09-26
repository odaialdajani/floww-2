"""Actual local HTTP transport checks on development-only inputs, not held-out answers."""
import copy

import pytest
from mongomock_motor import AsyncMongoMockClient

from scripts.research_comparison_inputs import history_inputs, synthetic_chain
from scripts.research_comparison_transport import exercise
from services.agent.repository import AgentRepository


def development_item():
    return {'id': 'development_transport_only',
            'body': {'question': 'What is the spot price of $SPY?', 'ticker': 'SPY', 'horizon': 'all',
                     'screen': {'ticker': 'SPY', 'page': 'heatseeker', 'horizon': 'all'}},
            'clock': {'at': '2026-09-28T14:30:00Z'},
            'chains': {'SPY': synthetic_chain('SPY', {'spot': 123.45})},
            'maps': {}, 'alerts': {'mode': 'controlled_empty_alerts', 'parameters': {}}, 'history': {}}


class ForbiddenModel:
    async def once(self, *args, **kwargs):
        raise AssertionError('Development price/refusal test attempted model work')


@pytest.mark.asyncio
async def test_actual_http_reports_saved_reopen_privacy_and_read_counts():
    repo = AgentRepository(AsyncMongoMockClient(tz_aware=True).test)
    await repo.initialize()
    item = development_item()
    before = copy.deepcopy(item)
    report = await exercise(item, repo, model_factory=lambda trace: ForbiddenModel())
    assert report['http_status'] == 200 and report['errors'] == []
    assert report['saved_turn']['status'] == 'completed'
    assert report['read_metrics']['started'] == 1
    assert report['trace']['model_invocations'] == 0
    assert report['trace']['measurement_complete'] is True
    assert report['trace']['first_browser_display_s'] is None
    assert report['trace']['timings_s']['first_stream_progress_received'] >= 0
    assert report['saved_reopen_identical'] and report['private_history_present'] and report['other_owner_status'] == 404
    assert report['alert_query_receipts'] == []
    price = next(f for f in report['saved_turn']['answer']['facts'] if f['metric'] == 'Underlying price')
    assert price['value'] == 123.45
    assert item == before


@pytest.mark.asyncio
async def test_actual_pre_admission_refusal_has_no_turn_or_reads():
    repo = AgentRepository(AsyncMongoMockClient(tz_aware=True).test)
    await repo.initialize()
    item = development_item()
    item['body']['screen']['overlayMetric'] = 'activity'
    result = await exercise(item, repo, expected_status=422, model_factory=lambda trace: ForbiddenModel())
    assert result['http_status'] == 422 and result['errors'] == []
    assert result['owned_turn_count'] == 0 and result['alert_query_receipts'] == []
    assert result['trace']['model_invocations'] == 0
    assert result['trace']['measurement_complete']
    assert result['read_entry_evidence']['snapshot_entries'] == []
    assert result['read_entry_evidence']['source_callbacks'] == []


@pytest.mark.asyncio
async def test_development_history_uses_real_route_and_saved_prior_anchor():
    repo = AgentRepository(AsyncMongoMockClient(tz_aware=True).test)
    await repo.initialize()
    item = development_item()
    item['body']['question'] = 'Since my prior $SPY observation, how much did its saved price change?'
    item['history'] = history_inputs(item['chains'], {'variant': 'matching_coverage', 'prior_price': 119, 'current_price': 123.45})
    result = await exercise(item, repo)
    assert result['errors'] == [] and len(result['history_seed']) == 1
    change = next(f for f in result['saved_turn']['answer']['facts'] if f['metric'] == 'Price change since saved observation')
    assert change['value'] == pytest.approx(4.45)
    assert result['read_metrics']['started'] == 2
    assert result['saved_reopen_identical']


@pytest.fixture(autouse=True)
def refuse_external_network(monkeypatch):
    import socket
    connect, connect_ex = socket.socket.connect, socket.socket.connect_ex
    def allowed(method):
        def guard(sock, address):
            if not isinstance(address, tuple) or address[0] not in {'127.0.0.1', '::1'}:
                raise AssertionError('Development comparison attempted external network')
            return method(sock, address)
        return guard
    monkeypatch.setattr(socket.socket, 'connect', allowed(connect))
    monkeypatch.setattr(socket.socket, 'connect_ex', allowed(connect_ex))


@pytest.mark.asyncio
async def test_service_close_failure_still_stops_owned_listener():
    import asyncio

    from scripts.research_comparison_transport import local_server
    class BrokenClose:
        async def close(self):
            raise RuntimeError('development close failure')
    before = set(asyncio.all_tasks())
    with pytest.raises(RuntimeError, match='close failure'):
        async with local_server(BrokenClose()):
            pass
    remaining = [task for task in asyncio.all_tasks() - before if not task.done()]
    assert not remaining


@pytest.mark.asyncio
async def test_noncooperative_service_cleanup_is_bounded_and_reported(monkeypatch):
    import asyncio

    import scripts.research_comparison_transport as transport
    release = asyncio.Event()
    class DelayedClose:
        async def close(self):
            try:
                await release.wait()
            except asyncio.CancelledError:
                await release.wait()
    monkeypatch.setattr(transport, '_CLEANUP_SECONDS', .2)
    before = set(asyncio.all_tasks())
    try:
        async with asyncio.timeout(2):
            with pytest.raises(RuntimeError, match='discard evaluation process'):
                async with transport.local_server(DelayedClose()):
                    pass
    finally:
        release.set()
        owned = list(asyncio.all_tasks() - before)
        if owned:
            await asyncio.gather(*owned, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancelled_context_waits_for_cooperative_close():
    import asyncio

    from scripts.research_comparison_transport import local_server
    entered = asyncio.Event()
    class CooperativeClose:
        async def close(self):
            entered.set()
            await asyncio.Event().wait()
    before = set(asyncio.all_tasks())
    async def context_owner():
        async with local_server(CooperativeClose()):
            pass
    owner = asyncio.create_task(context_owner())
    await entered.wait()
    owner.cancel()
    with pytest.raises(asyncio.CancelledError):
        await owner
    assert not [task for task in asyncio.all_tasks() - before if not task.done()]


@pytest.mark.asyncio
async def test_cancel_during_listener_shutdown_waits_for_exit():
    import asyncio

    from scripts.research_comparison_transport import local_server
    closed = asyncio.Event()
    class QuickClose:
        async def close(self):
            closed.set()
    before = set(asyncio.all_tasks())
    async def context_owner():
        async with local_server(QuickClose()):
            pass
    owner = asyncio.create_task(context_owner())
    await closed.wait()
    await asyncio.sleep(.005)
    owner.cancel()
    with pytest.raises(asyncio.CancelledError):
        await owner
    assert not [task for task in asyncio.all_tasks() - before if not task.done()]

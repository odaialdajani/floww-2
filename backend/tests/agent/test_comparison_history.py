"""Prior fixture preparation uses real saved anchors, never fabricated answers."""
import copy
import json
from pathlib import Path

import pytest
from mongomock_motor import AsyncMongoMockClient

from scripts.research_comparison_history import current_snapshot, seed_history
from scripts.research_comparison_inputs import prepare_case
from services.agent.repository import AgentRepository
from services.agent.saved_history import history_facts

ROOT = Path(__file__).resolve().parents[3]


def prepared(identity):
    proposal = json.loads((ROOT / '.planning/eval/research-fresh-comparison-proposal-20260926-v3.json').read_text())
    return prepare_case(next(case for case in proposal['cases'] if case['id'] == identity), {})


@pytest.mark.asyncio
@pytest.mark.parametrize('identity,count,change', [
    ('owned_price_change', 1, 2),
    ('history_changed_selection', 1, None),
    ('other_owner_history', 1, None),
    ('late_snapshot_not_close', 1, None),
    ('three_ticker_history_budget', 3, 2),
])
async def test_prior_fixture_exercises_actual_owned_history(identity, count, change):
    item = prepared(identity)
    original = copy.deepcopy(item)
    repo = AgentRepository(AsyncMongoMockClient().test)
    await repo.initialize()
    owner, _ = await repo.session()
    receipt = await seed_history(repo, owner, item)
    assert len(receipt) == count
    assert await repo.turns.count_documents({}) == 0
    assert await repo.snapshots.count_documents({}) == count
    for ticker in item['history']:
        current = await current_snapshot(item, ticker)
        facts, note = await history_facts(repo, owner, current, closing_only=identity == 'late_snapshot_not_close')
        if change is None:
            assert facts == []
            if identity == 'history_changed_selection':
                assert 'earlier saved coverage: 4 contracts; current saved coverage: 2 contracts' in note
            elif identity == 'other_owner_history':
                assert '100' not in note and '14:25' not in note
            else:
                assert '2026-09-28T20:00:00' in note
        else:
            assert facts[-1]['value'] == change
            assert facts[-1]['parents'][0] == facts[0]['id']
        assert (await history_facts(repo, 'unrelated-owner', current))[0] == []
    assert item == original


@pytest.mark.asyncio
async def test_seed_refuses_nonempty_owner_before_mutating_store():
    repo = AgentRepository(AsyncMongoMockClient().test)
    await repo.initialize()
    owner, _ = await repo.session()
    item = prepared('owned_price_change')
    await seed_history(repo, owner, item)
    with pytest.raises(ValueError, match='empty'):
        await seed_history(repo, owner, item)
    assert await repo.snapshots.count_documents({}) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', ['future_prior', 'wrong_ticker', 'missing_time', 'wrong_difference', 'wrong_owner_relation'])
async def test_invalid_history_recipe_refuses_before_first_save(mutation):
    repo = AgentRepository(AsyncMongoMockClient().test)
    await repo.initialize()
    owner, _ = await repo.session()
    item = prepared('owned_price_change')
    prior = item['history']['IWM']
    if mutation == 'future_prior':
        prior['prior_raw']['spot_event_time'] = '2026-09-28T14:31:00Z'
    elif mutation == 'wrong_ticker':
        prior['prior_raw']['ticker'] = 'QQQ'
    elif mutation == 'missing_time':
        prior['prior_raw']['spot_event_time'] = None
    elif mutation == 'wrong_difference':
        prior['raw_price_difference'] = 7
    else:
        prior['same_owner'] = False
    with pytest.raises(ValueError):
        await seed_history(repo, owner, item)
    assert await repo.snapshots.count_documents({}) == 0
    assert await repo.turns.count_documents({}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', ['missing_ticker', 'empty', 'future_chain', 'future_iv', 'wrong_anchor', 'already_inserted'])
async def test_incomplete_or_incoherent_history_refuses_before_saving(mutation):
    repo = AgentRepository(AsyncMongoMockClient().test)
    await repo.initialize()
    owner, _ = await repo.session()
    item = prepared('three_ticker_history_budget')
    prior = item['history']['QQQ']
    if mutation == 'missing_ticker':
        del item['history']['DIA']
    elif mutation == 'empty':
        item['history'] = {}
    elif mutation == 'future_chain':
        prior['prior_raw']['event_time'] = '2026-09-28T14:29:50Z'
    elif mutation == 'future_iv':
        prior['prior_raw']['contracts'][0]['iv_event_time'] = '2026-09-28T14:29:50Z'
    elif mutation == 'wrong_anchor':
        prior['prior_anchor_kind'] = 'intraday'
    else:
        prior['store_inserted'] = True
    with pytest.raises(ValueError):
        await seed_history(repo, owner, item)
    assert await repo.snapshots.count_documents({}) == 0


@pytest.mark.asyncio
async def test_second_write_failure_rolls_back_only_attempted_owner_anchors(monkeypatch):
    repo = AgentRepository(AsyncMongoMockClient().test)
    await repo.initialize()
    owner, _ = await repo.session()
    await repo.snapshots.insert_one({'owner': 'unrelated', 'snapshot': {'snapshot_id': 'keep'}})
    original = repo.save_anchor
    calls = 0
    async def fail_after_write(target, snapshot):
        nonlocal calls
        calls += 1
        await original(target, snapshot)
        if calls == 2:
            raise RuntimeError('write acknowledgment lost')
    monkeypatch.setattr(repo, 'save_anchor', fail_after_write)
    with pytest.raises(RuntimeError, match='rolled back'):
        await seed_history(repo, owner, prepared('three_ticker_history_budget'))
    assert await repo.snapshots.count_documents({'owner': owner}) == 0
    assert await repo.snapshots.count_documents({'owner': 'unrelated'}) == 1


@pytest.mark.asyncio
async def test_expired_session_is_refused_even_before_ttl_cleanup():
    from datetime import UTC, datetime, timedelta
    repo = AgentRepository(AsyncMongoMockClient().test)
    await repo.initialize()
    owner, _ = await repo.session()
    await repo.sessions.drop_index('expires_at_1')
    await repo.sessions.update_one({'owner': owner}, {'$set': {'expires_at': datetime.now(UTC) - timedelta(seconds=1)}})
    assert await repo.sessions.count_documents({'owner': owner}) == 1
    with pytest.raises(ValueError, match='session'):
        await seed_history(repo, owner, prepared('owned_price_change'))
    assert await repo.snapshots.count_documents({}) == 0

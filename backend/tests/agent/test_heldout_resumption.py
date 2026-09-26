"""Resuming acceptance must preserve frozen cases and the original usage ledger."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import oauth_heldout_v2 as run


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    eval_dir = tmp_path / 'eval'
    eval_dir.mkdir()
    source = tmp_path / 'source.py'
    source.write_text('new code', encoding='utf-8')
    original = eval_dir / 'oauth-heldout-v2-inputs.json'
    old_seal = eval_dir / 'oauth-heldout-v2-execution-seal.json'
    proposal = eval_dir / 'proposal.json'
    proposal.write_text('{}', encoding='utf-8')
    prior = {'cases': [{'id': str(i), 'body': {'question': 'fixed'}} for i in range(30)],
             'code': {'source.py': 'previous'}, 'proposal': {'path': 'eval/proposal.json', 'sha256': run.sha(proposal)},
             'candidate': {'model': 'same'}, 'required_model_allowance': 26}
    original.write_text(json.dumps(prior), encoding='utf-8')
    old_seal.write_text(json.dumps({'inputs_sha256': run.sha(original)}), encoding='utf-8')
    monkeypatch.setattr(run, 'ROOT', tmp_path)
    monkeypatch.setattr(run, 'EVAL', eval_dir)
    monkeypatch.setattr(run, 'BOUND', original)
    monkeypatch.setattr(run, 'SEAL', old_seal)
    monkeypatch.setattr(run, 'USAGE_URI', run.DATA_URI)
    monkeypatch.setattr(run, 'execution_seal', lambda: {'inputs_sha256': run.sha(run.BOUND)})
    return original, old_seal, prior


def test_refreeze_retains_all_original_case_and_candidate_bytes(frozen):
    original, old_seal, prior = frozen
    before = original.read_bytes(), old_seal.read_bytes()
    run.select_revision('resume-test', 'mongodb://127.0.0.1:27018')
    assert run.refreeze()['model_calls'] == 0
    new = run.read(run.BOUND)
    assert new['cases'] == prior['cases']
    assert new['candidate'] == prior['candidate']
    assert new['code']['source.py'] == run.sha(run.ROOT / 'source.py')
    assert (original.read_bytes(), old_seal.read_bytes()) == before
    assert new['resumption']['usage_anchor']['minimum_calls'] == 34
    with pytest.raises(ValueError, match='unused revision'):
        run.refreeze()
    assert (original.read_bytes(), old_seal.read_bytes()) == before


def test_changed_original_input_cannot_be_refrozen(frozen):
    original, _, _ = frozen
    original.write_text(original.read_text() + ' ', encoding='utf-8')
    run.select_revision('bad-parent', 'mongodb://127.0.0.1:27018')
    with pytest.raises(ValueError, match='preserved seal'):
        run.refreeze()
    assert not run.BOUND.exists()


@pytest.mark.parametrize('label,uri', [('../old','mongodb://127.0.0.1:27018'),
                                     ('okay','mongodb://remote:27018')])
def test_unsafe_revision_or_usage_endpoint_refused(frozen, label, uri):
    with pytest.raises(ValueError):
        run.select_revision(label, uri)


@pytest.mark.asyncio
@pytest.mark.parametrize('condition', ['empty-ledger', 'bad-baseline', 'low-budget', 'model-unavailable'])
async def test_preflight_refuses_without_dispatch_and_closes_both_clients(tmp_path, monkeypatch, condition):
    clients = []
    class Client:
        def __init__(self, *args, **kwargs):
            self.closed = False
            clients.append(self)
        def __getitem__(self, key):
            return self
        def __getattr__(self, key):
            return self
        async def find_one(self, query):
            return None if condition == 'empty-ledger' else {'calls': 34}
        def close(self):
            self.closed = True
    class Model:
        def __init__(self, *args):
            self.spend = self
        async def state(self):
            return {'daily_limit': 40, 'calls': 39 if condition == 'low-budget' else 0}
        async def validate_settings(self, settings):
            raise ValueError('model unavailable')
    bound = {'proposal': {}, 'code': {}, 'cases': [{}] * 30,
             'required_model_allowance': 26, 'candidate': {},
             'resumption': {'usage_anchor': {'_id': 'day:2026-09-11', 'minimum_calls': 34}}}
    for item in bound['cases']:
        item.update(chains={}, maps={}, expected=None, prior=None)
    monkeypatch.setattr(run, 'BOUND', tmp_path / 'bound')
    monkeypatch.setattr(run, 'SEAL', tmp_path / 'seal')
    monkeypatch.setattr(run, 'sha', lambda _: 'hash')
    monkeypatch.setattr(run, 'execution_seal', lambda: {'sealed': True})
    def read(path):
        if path == run.BOUND:
            return bound
        if path == run.SEAL:
            return {'sealed': True}
        return {'status': 'FAILED' if condition == 'bad-baseline' else 'ROUTE_CHECKS_PASSED',
                'inputs_sha256': 'hash', 'execution_seal_sha256': 'hash', 'cases': []}
    monkeypatch.setattr(run, 'read', read)
    monkeypatch.setattr(run, 'resolve', lambda _: {})
    monkeypatch.setattr(run, 'validate_resumption', lambda b: b['resumption']['usage_anchor'])
    monkeypatch.setattr(run, 'AsyncIOMotorClient', Client)
    monkeypatch.setattr(run, 'AgentRepository', lambda _: SimpleNamespace())
    monkeypatch.setattr(run, 'CodexModel', Model)
    with pytest.raises(ValueError):
        await run.execute('run', tmp_path / 'output', Path('baseline'))
    assert len(clients) == 2 and all(c.closed for c in clients)
    assert not (tmp_path / 'output').exists()


@pytest.mark.parametrize('mutation', ['parent', 'missing-anchor', 'cases', 'candidate'])
def test_revision_validates_parent_lineage_and_preserved_fields(frozen, mutation):
    original, _, _ = frozen
    run.select_revision('lineage-test', 'mongodb://127.0.0.1:27018')
    run.refreeze()
    bound = run.read(run.BOUND)
    assert run.validate_resumption(bound)['minimum_calls'] == 34
    if mutation == 'parent':
        original.write_text(original.read_text() + ' ', encoding='utf-8')
    elif mutation == 'missing-anchor':
        del bound['resumption']
    elif mutation == 'cases':
        bound['cases'][0]['body']['question'] = 'changed'
    elif mutation == 'candidate':
        bound['candidate'] = {'model': 'changed'}
    with pytest.raises(ValueError):
        run.validate_resumption(bound)


@pytest.mark.parametrize('mode', ['prepare', 'seal'])
def test_revision_cannot_use_original_preparation_path(monkeypatch, mode):
    monkeypatch.setattr('sys.argv', ['runner', mode, '--revision', 'unsafe'])
    with pytest.raises(SystemExit) as exc:
        run.main()
    assert exc.value.code == 2

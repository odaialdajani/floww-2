"""Control-path tests use invented development cases, never the frozen comparison."""
import copy
from datetime import UTC, datetime

import pytest

pytest.importorskip("mongomock_motor", reason="mongo mock unavailable in this env")
from mongomock_motor import AsyncMongoMockClient

from scripts import research_comparison_run as run
from scripts.research_comparison_inputs import json_bytes


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    (tmp_path / 'backend').mkdir()
    (tmp_path / 'backend' / 'development.py').write_text('DEVELOPMENT = True\n')
    monkeypatch.setattr(run, 'environment_identity', lambda root: {'source_files': run.source_identity(root)})
    monkeypatch.setattr(run, 'display_identity', lambda root: {'files': {'development': 'display-only'}})
    ids = ['development_' + str(i) for i in range(32)]
    critical_ids = ['development_critical_' + str(i) for i in range(14)]
    files = tmp_path / 'inputs'
    files.mkdir()
    manifest = {'cases': []}
    oracle = {'cases': [], 'unresolved_cases': []}
    proposal = {'cases': [{'id': i, 'body': {'question': 'Explain $SPY', 'ticker': 'SPY'},
                          'expected': {'model_route': {'inexpensive': 'eligible'}}} for i in ids], 'critical_cases': [{'id': i} for i in critical_ids], 'source_catalog': []}
    def save(name, obj):
        path = tmp_path / (name + '.json')
        path.write_bytes(json_bytes(obj))
        return path
    proposal_path = save('proposal', proposal)
    proposal_hash = run.reference(proposal_path)['sha256']
    for case_id in ids:
        path = files / (case_id + '.json')
        path.write_bytes(json_bytes({'id': case_id, 'development_only': True}))
        ref = run.reference(path)
        manifest['cases'].append({'id': case_id, 'fixture': {'path': path.name, 'sha256': ref['sha256']}})
        oracle['cases'].append({'id': case_id, 'input': ref})
    manifest['proposal_sha256'] = proposal_hash
    (files / 'manifest.json').write_bytes(json_bytes(manifest))
    grading_path = save('grading', {'cases': [{'id': i} for i in ids], 'proposal_sha256': proposal_hash})
    oracle.update(proposal=run.reference(proposal_path), grading=run.reference(grading_path),
                  input_manifest=run.reference(files / 'manifest.json'))
    oracle_path = save('oracle', oracle)
    review_path = save('review', {})
    authority_path = save('authority', {'settings': {'inexpensive': {
        'model': 'gpt-5.6-terra', 'effort': 'medium', 'speed': 'default'}}})
    args = (proposal_path, files, oracle_path, grading_path, review_path, authority_path)
    return tmp_path, args, save, ids, critical_ids


def prepare(bundle):
    root, args, *_ = bundle
    return run.prepare(*args, root=root)


def approve_development_fixture(bundle):
    root, args, save, ids, critical_ids = bundle
    proof = save('critical', {'proposal_sha256': run.reference(args[0])['sha256'],
                 'source_files': run.source_identity(root), 'cases': [{'id': i, 'status': 'passed'} for i in critical_ids]})
    save('review', {'status': 'approved_before_answers', 'bindings': {
        k: run.reference(p)['sha256'] for k, p in zip(('proposal', 'oracle', 'grading', 'manifest'),
                                                    (args[0], args[2], args[3], args[1] / 'manifest.json'), strict=True)},
        'closed_bindings': {}, 'critical_receipt': run.reference(proof),
        'quota_rule': 'whole_arm_preflight_per_turn_atomic_40_no_cohort_lock'})
    save('authority', {'settings': {'inexpensive': {'model': 'gpt-5.6-terra', 'effort': 'medium', 'speed': 'default'},
                                    'stronger': {'model': 'DEVELOPMENT_ONLY', 'effort': 'medium', 'speed': 'default'}},
                       'stronger_user_choice': 'invented control test, grants no real authorization',
                       'cost_user_choice': 'invented control test', 'cost_decision': 'accept_unknown_usd_under_call_limit'})
    return proof


def test_pending_choices_stop_before_seal(bundle):
    report = prepare(bundle)
    assert report['status'] == 'blocked'
    assert any('stronger-model' in b for b in report['blockers'])
    assert any('unknown-dollar' in b for b in report['blockers'])
    with pytest.raises(ValueError, match='incomplete'):
        run.seal(report, bundle[0] / 'seal.json')
    assert not (bundle[0] / 'seal.json').exists()


def test_changed_fixture_rejected_before_preparation(bundle):
    (bundle[1][1] / 'development_0.json').write_text('{}')
    with pytest.raises(ValueError, match='identity'):
        prepare(bundle)


def test_missing_case_cannot_shrink_denominator(bundle):
    path = bundle[1][1] / 'manifest.json'
    data = run.read_json(path)
    data['cases'].pop()
    path.write_bytes(json_bytes(data))
    with pytest.raises(ValueError, match='every case'):
        prepare(bundle)


def test_critical_receipt_is_frozen_and_source_bound(bundle, monkeypatch):
    proof = approve_development_fixture(bundle)
    prepared = prepare(bundle)
    assert prepared['status'] == 'prepared'
    exe = bundle[0] / 'development.exe'
    exe.write_bytes(b'never executed')
    monkeypatch.setattr('services.agent.codex_bridge.executable', lambda: str(exe))
    path = bundle[0] / 'sealed.json'
    run.seal(prepared, path)
    sha = run.reference(path)['sha256']
    assert run.verify_seal(path, sha, root=bundle[0])['status'] == 'sealed'
    proof.write_text('{}')
    with pytest.raises(ValueError, match='changed'):
        run.verify_seal(path, sha, root=bundle[0])


def test_added_source_invalidates_execution_identity(bundle, monkeypatch):
    approve_development_fixture(bundle)
    prepared = prepare(bundle)
    exe = bundle[0] / 'development.exe'
    exe.write_bytes(b'never executed')
    monkeypatch.setattr('services.agent.codex_bridge.executable', lambda: str(exe))
    path = bundle[0] / 'sealed.json'
    run.seal(prepared, path)
    (bundle[0] / 'backend' / 'new_source.py').write_text('NEW = 1')
    with pytest.raises(ValueError, match='source or dependencies'):
        run.verify_seal(path, run.reference(path)['sha256'], root=bundle[0])


def test_original_source_catalog_rechecked(bundle):
    root, args, save, *_ = bundle
    raw = root / 'raw.json'
    raw.write_text('{}')
    proposal = run.read_json(args[0])
    proposal['source_catalog'] = [{'id': 'development_raw', 'path': 'raw.json', 'sha256': run.reference(raw)['sha256']}]
    save('proposal', proposal)
    # A proposal changed after raw preparation is rejected rather than silently rebound.
    with pytest.raises(ValueError, match='Proposal binding differs'):
        prepare(bundle)


def test_actual_dollar_requirement_is_not_silently_waived(bundle):
    approve_development_fixture(bundle)
    auth = run.read_json(bundle[1][-1])
    auth['cost_decision'] = 'require_actual_usd'
    bundle[2]('authority', auth)
    assert any('actual dollar' in b for b in prepare(bundle)['blockers'])


@pytest.mark.asyncio
async def test_new_or_reset_usage_ledger_cannot_grant_headroom():
    coll = AsyncMongoMockClient().test.usage
    with pytest.raises(ValueError, match='history missing or reset'):
        await run.quota_preflight(coll, 32)


@pytest.mark.asyncio
async def test_complete_candidate_preflight_preserves_shared_limit():
    coll = AsyncMongoMockClient().test.usage
    for day, calls in run.HISTORICAL_MINIMUMS.items():
        await coll.insert_one({'_id': 'day:' + day, 'calls': calls})
    day = datetime.now(UTC).date().isoformat()
    await coll.update_one({'_id': 'day:' + day}, {'$set': {'calls': 40}}, upsert=True)
    before = await coll.find_one({'_id': 'day:' + day})
    with pytest.raises(ValueError, match='does not fit'):
        await run.quota_preflight(coll, 1)
    assert await coll.find_one({'_id': 'day:' + day}) == before
    assert (await run.quota_preflight(coll, 0))['cohort_reservation'] is False


@pytest.mark.asyncio
async def test_model_candidate_refused_without_execution_flag(tmp_path, monkeypatch):
    monkeypatch.setattr(run, 'verify_seal', lambda *a, **k: {})
    with pytest.raises(ValueError, match='explicit execution'):
        await run.execute(tmp_path / 'seal', 'test', 'inexpensive', tmp_path / 'out')
    assert not (tmp_path / 'out').exists()


@pytest.mark.asyncio
async def test_failed_attempt_stays_unknown_and_cannot_reexecute_new_directory(tmp_path, monkeypatch):
    fixtures = []
    for i in range(32):
        path = tmp_path / (str(i) + '.json')
        path.write_bytes(json_bytes({'id': 'development_' + str(i)}))
        fixtures.append({'id': 'development_' + str(i), **run.reference(path)})
    proposal = tmp_path / 'proposal.json'
    proposal.write_bytes(json_bytes({'cases': [{'id': f['id'], 'expected': {'model_route': {
        'inexpensive': 'deterministic_price_bypass'}}} for f in fixtures]}))
    sealed = {'fixtures': fixtures, 'settings': {}, 'artifacts': {'proposal': run.reference(proposal)}}
    monkeypatch.setattr(run, 'verify_seal', lambda *a, **k: copy.deepcopy(sealed))
    client = AsyncMongoMockClient(tz_aware=True)
    monkeypatch.setattr('motor.motor_asyncio.AsyncIOMotorClient', lambda *a, **k: client)
    entries = []
    async def interrupted(*args, **kwargs):
        kwargs['admission_sink']({'stage': 'before_request', 'owner': 'development-owner', 'request_id': 'development-id'})
        entries.append('entered')
        raise RuntimeError('development interrupted after entry')
    monkeypatch.setattr('scripts.research_comparison_transport.exercise', interrupted)
    out = tmp_path / 'first'
    with pytest.raises(RuntimeError, match='interrupted'):
        await run.execute(tmp_path / 'seal', 'development-seal', 'deterministic', out)
    final = run.read_json(out / 'final.json')
    assert len(final['cases']) == 32 and not final['complete_execution']
    assert final['cases'][0]['status'] == 'started_outcome_unknown'
    assert all(c['status'] == 'not_run' for c in final['cases'][1:])
    assert run.read_json(out / 'development_0.before_request.json')['owner'] == 'development-owner'
    with pytest.raises(Exception, match='Duplicate Key'):
        await run.execute(tmp_path / 'seal', 'development-seal', 'deterministic', tmp_path / 'second')
    assert entries == ['entered']


def test_environment_identity_survives_json_roundtrip(tmp_path):
    import json
    (tmp_path / 'backend').mkdir()
    (tmp_path / 'backend' / 'development.py').write_text('X = 1')
    identity = run.environment_identity(tmp_path)
    assert json.loads(json.dumps(identity)) == identity


def test_resealing_does_not_create_a_new_cohort(bundle, monkeypatch):
    approve_development_fixture(bundle)
    prepared = prepare(bundle)
    exe = bundle[0] / 'development.exe'
    exe.write_bytes(b'never executed')
    monkeypatch.setattr('services.agent.codex_bridge.executable', lambda: str(exe))
    first = run.seal(prepared, bundle[0] / 'first-seal.json')
    second = run.seal(prepared, bundle[0] / 'second-seal.json')
    assert first['cohort_identity'] == second['cohort_identity']


def test_reference_hash_and_decode_use_identical_bytes(tmp_path, monkeypatch):
    from pathlib import Path
    path = tmp_path / 'one.json'
    path.write_bytes(b'{"value": 1}')
    ref = run.reference(path)
    reads = []
    original = Path.read_bytes
    def changing_read(target):
        if target == path:
            reads.append(1)
            return b'{"value": 1}' if len(reads) == 1 else b'{"value": 2}'
        return original(target)
    monkeypatch.setattr(Path, 'read_bytes', changing_read)
    assert run.read_reference(ref) == {'value': 1}
    assert len(reads) == 1


def test_display_drift_invalidates_execution_identity(bundle, monkeypatch):
    approve_development_fixture(bundle)
    prepared = prepare(bundle)
    exe = bundle[0] / 'development.exe'
    exe.write_bytes(b'never executed')
    monkeypatch.setattr('services.agent.codex_bridge.executable', lambda: str(exe))
    path = bundle[0] / 'sealed.json'
    run.seal(prepared, path)
    monkeypatch.setattr(run, 'display_identity', lambda root: {'files': {'development': 'changed'}})
    with pytest.raises(ValueError, match='source or dependencies'):
        run.verify_seal(path, run.reference(path)['sha256'], root=bundle[0])


def test_prospective_request_spec_binds_actual_scope_and_refusal():
    cases = [dict(id='development_valid', body={'question': 'Explain $SPY next month', 'ticker': 'SPY'},
                  expected={'model_route': {'inexpensive': 'eligible'}}),
             dict(id='development_refused', body={'question': 'Compare $SPY $QQQ $IWM $AAPL'},
                  expected={'model_route': {'inexpensive': 'no_model_before_validation'}})]
    specs = run.bind_request_specs(cases)
    assert specs['development_valid']['horizon'] == 'month'
    assert specs['development_refused'] is None
    cases[1]['expected']['model_route']['inexpensive'] = 'eligible'
    with pytest.raises(ValueError, match='admitted comparison request is invalid'):
        run.bind_request_specs(cases)

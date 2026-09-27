"""Seal and execute the reviewed three-arm research comparison.

Preparation is read-only and never authorizes a model call. A seal requires the
existing user choices, closed independent bindings and actual critical receipts.
Execution never resumes an old output directory or retries an uncertain case.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import json
import os
import secrets
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from scripts.research_comparison_inputs import checked_path, digest, json_bytes

ROOT = Path(__file__).resolve().parents[2]
ARMS = ('deterministic', 'inexpensive', 'stronger')
USAGE_URI = 'mongodb://127.0.0.1:27018'
USAGE_DB = 'floww_public_research_acceptance'
HISTORICAL_MINIMUMS = {'2026-09-11': 34, '2026-09-26': 25}


def read_json(path):
    return json.loads(path.read_bytes())


def reference(path):
    path = path.resolve()
    return {'path': str(path), 'sha256': digest(path.read_bytes())}


def read_reference(ref):
    path = Path(ref['path'])
    raw = path.read_bytes()
    if not path.is_absolute() or digest(raw) != ref['sha256']:
        raise ValueError('Frozen artifact changed: ' + str(path))
    return json.loads(raw)


def exclusive_json(path, value):
    with path.open('xb') as stream:
        stream.write(json_bytes(value))
        stream.flush()
        os.fsync(stream.fileno())


def source_identity(root):
    """Conservative backend source inventory, including additions/removals."""
    files = {}
    for folder, names, leaves in os.walk(root / 'backend'):
        names[:] = sorted(n for n in names if n not in {
            '.venv', 'venv', '__pycache__', '.git', 'node_modules', '.pytest_cache', '.ruff_cache',
        } and not n.startswith('.venv'))
        for name in sorted(leaves):
            if name.endswith('.py') or name.startswith('requirements') or name == 'pyproject.toml':
                path = Path(folder) / name
                files[path.relative_to(root).as_posix()] = digest(path.read_bytes())
    if not files:
        raise ValueError('No backend source inventory')
    return files


DISPLAY_FILES = (
    'src/agent/AgentPanelAnswer.jsx', 'src/agent/Evidence.jsx',
    'src/agent/chartReading.js', 'src/agent/AgentModelSettings.jsx', 'src/config/api.js',
    'src/agent/useAgentStream.js', 'src/agent/AgentProvider.jsx', 'src/agent/AgentConversation.jsx',
    'scripts/render-comparison-packet.cjs', 'package.json', 'package-lock.json',
)


def display_identity(root):
    return {'files': {name: digest((root / 'frontend' / name).read_bytes()) for name in DISPLAY_FILES}}


def environment_identity(root):
    return {
        'source_files': source_identity(root),
        'python': reference(Path(sys.executable)),
        'python_version': sys.version,
        'packages': sorted([d.metadata['Name'], d.version] for d in importlib.metadata.distributions()),
    }


def require_ids(rows, expected, label):
    ids = [row['id'] for row in rows]
    if ids != expected or len(set(ids)) != len(ids):
        raise ValueError(label + ' must preserve every case in order')


def bind_request_specs(cases):
    from services.agent.contracts import request_spec
    specs = {}
    for case in cases:
        refused = case['expected']['model_route']['inexpensive'] == 'no_model_before_validation'
        try:
            spec = request_spec(case['body'])
        except ValueError:
            if not refused:
                raise ValueError('An admitted comparison request is invalid') from None
            spec = None
        else:
            if refused:
                raise ValueError('A refused comparison request is unexpectedly valid')
        specs[case['id']] = spec
    return specs


def prepare(proposal_path, bundle, oracle_path, grading_path, review_path, authority_path, root=ROOT):
    paths = dict(proposal=proposal_path, manifest=bundle / 'manifest.json',
                 oracle=oracle_path, grading=grading_path, review=review_path, authority=authority_path)
    refs = {name: reference(path) for name, path in paths.items()}
    docs = {name: read_reference(ref) for name, ref in refs.items()}
    proposal, manifest, oracle, grading, review, authority = (docs[k] for k in paths)
    ids = [c['id'] for c in proposal['cases']]
    if len(ids) != 32 or len(set(ids)) != 32:
        raise ValueError('Exactly 32 distinct functional cases required')
    critical_ids = [c['id'] for c in proposal['critical_cases']]
    if len(critical_ids) != 14 or len(set(critical_ids)) != 14:
        raise ValueError('Exactly 14 distinct critical checks required')
    for name in ('manifest', 'oracle', 'grading'):
        require_ids(docs[name]['cases'], ids, name)
    proposal_hash = refs['proposal']['sha256']
    if manifest['proposal_sha256'] != proposal_hash or grading['proposal_sha256'] != proposal_hash:
        raise ValueError('Proposal binding differs')
    for name in ('proposal', 'grading', 'input_manifest'):
        target = 'manifest' if name == 'input_manifest' else name
        if oracle[name]['sha256'] != refs[target]['sha256']:
            raise ValueError('Independent oracle binding differs')
    fixtures = []
    for row, independent in zip(manifest['cases'], oracle['cases'], strict=True):
        ref = reference(checked_path(bundle, row['fixture']['path']))
        item = read_reference(ref)
        if (ref['sha256'] != row['fixture']['sha256'] or independent['input']['sha256'] != ref['sha256']
                or item['id'] != row['id']):
            raise ValueError('Raw input identity differs')
        fixtures.append({'id': row['id'], **ref})
    # Original referenced bytes stay verifiable even when only raw subsets are used.
    sources = []
    for row in proposal['source_catalog']:
        ref = reference(checked_path(root, row['path']))
        if ref['sha256'] != row['sha256']:
            raise ValueError('Original source changed: ' + row['id'])
        sources.append(ref)
    identity = environment_identity(root)
    display = display_identity(root)
    blockers = []
    required_review = {'proposal': proposal_hash, 'oracle': refs['oracle']['sha256'],
                       'grading': refs['grading']['sha256'], 'manifest': refs['manifest']['sha256']}
    if review.get('bindings') != required_review or review.get('status') != 'approved_before_answers':
        blockers.append('Independent raw values, grading and route bindings need completed review')
    unresolved = {c['id'] for c in oracle.get('unresolved_cases', [])}
    closed = review.get('closed_bindings', {})
    if unresolved - {key for key, evidence in closed.items() if isinstance(evidence, list) and evidence}:
        blockers.append('Independent unresolved bindings remain open')
    attachments = []
    for evidence in closed.values():
        if not isinstance(evidence, list):
            raise ValueError('Closed binding requires evidence references')
        for ref in evidence:
            if not isinstance(ref, dict):
                raise ValueError('Closed binding requires hashed evidence')
            if digest(Path(ref['path']).read_bytes()) != ref['sha256']:
                raise ValueError('Binding evidence changed')
            attachments.append(ref)
    critical = review.get('critical_receipt')
    if critical is None:
        blockers.append('Actual critical-check receipt is missing')
    else:
        proof = read_reference(critical)
        attachments.append(critical)
        require_ids(proof['cases'], critical_ids, 'Critical receipt')
        if (proof.get('proposal_sha256') != proposal_hash or proof.get('source_files') != identity['source_files']
                or any(c.get('status') != 'passed' for c in proof['cases'])):
            blockers.append('Critical receipt is incomplete or uses different source')
    if review.get('quota_rule') != 'whole_arm_preflight_per_turn_atomic_40_no_cohort_lock':
        blockers.append('Prospective quota clarification has not been bound')
    settings = authority.get('settings', {})
    if settings.get('inexpensive') != {'model': 'gpt-5.6-terra', 'effort': 'medium', 'speed': 'default'}:
        blockers.append('Existing approved inexpensive settings are not preserved')
    stronger = settings.get('stronger')
    if (not isinstance(stronger, dict) or set(stronger) != {'model', 'effort', 'speed'}
            or not all(isinstance(v, str) and v for v in stronger.values())
            or not authority.get('stronger_user_choice')):
        blockers.append('Earlier stronger-model choice is unanswered')
    if authority.get('cost_decision') not in {'accept_unknown_usd_under_call_limit', 'require_actual_usd'}:
        blockers.append('Earlier unknown-dollar-cost choice is unanswered')
    elif authority['cost_decision'] == 'require_actual_usd':
        blockers.append('Managed route does not provide required actual dollar costs')
    if not authority.get('cost_user_choice'):
        blockers.append('Cost choice has no user reply recorded')
    result = dict(version=1, status='blocked' if blockers else 'prepared', blockers=blockers,
                  artifacts=refs, fixtures=fixtures, original_sources=sources, attachments=attachments, environment=identity, expected_display=display,
                  settings=settings, request_specs=bind_request_specs(proposal['cases']), functional_count=32, critical_count=14,
                  quota_rule='whole_arm_preflight_per_turn_atomic_40_no_cohort_lock',
                  maximum_reservations_per_candidate=32,
                  limits=['No acceptance or browser-paint proof from execution alone',
                          'Model method entries, managed dispatch and upstream requests are distinct',
                          'Whole-arm headroom is a preflight, not a cohort reservation'])
    # Detect concurrent edits across preparation, including a changed source inventory.
    for ref in [*refs.values(), *fixtures, *sources, *attachments]:
        if digest(Path(ref['path']).read_bytes()) != ref['sha256']:
            raise ValueError('Input changed during preparation')
    if environment_identity(root) != identity or display_identity(root) != display:
        raise ValueError('Source or environment changed during preparation')
    return result


def cohort_identity(fixtures):
    return digest(json_bytes([{'id': ref['id'], 'sha256': ref['sha256']} for ref in fixtures]))


def seal(prepared, output):
    if prepared['status'] != 'prepared' or prepared['blockers']:
        raise ValueError('Cannot seal incomplete comparison preparation')
    from services.agent.codex_bridge import executable
    labels = list(ARMS)
    secrets.SystemRandom().shuffle(labels)
    sealed = dict(prepared, status='sealed', cohort_identity=cohort_identity(prepared['fixtures']), sealed_at=datetime.now(UTC).isoformat(),
                  managed_executable=reference(Path(executable())),
                  private_blind_assignment=dict(zip(('arm_a', 'arm_b', 'arm_c'), labels, strict=True)))
    exclusive_json(output, sealed)
    return sealed


def verify_seal(path, expected_hash, root=ROOT):
    raw = path.read_bytes()
    if digest(raw) != expected_hash:
        raise ValueError('Seal identity differs')
    sealed = json.loads(raw)
    if sealed.get('cohort_identity') != cohort_identity(sealed['fixtures']):
        raise ValueError('Cohort identity differs')
    if sealed['status'] != 'sealed' or sealed['blockers']:
        raise ValueError('Comparison is not sealed')
    for ref in [*sealed['artifacts'].values(), *sealed['fixtures'], *sealed['original_sources'], *sealed['attachments']]:
        if digest(Path(ref['path']).read_bytes()) != ref['sha256']:
            raise ValueError('Frozen source or input changed')
    if environment_identity(root) != sealed['environment'] or display_identity(root) != sealed['expected_display']:
        raise ValueError('Execution source or dependencies changed')
    from services.agent.codex_bridge import executable
    if reference(Path(executable())) != sealed['managed_executable']:
        raise ValueError('Managed executable changed')
    return sealed


async def quota_preflight(collection, required):
    if type(required) is not int or not 0 <= required <= 32:
        raise ValueError('Invalid complete-arm allowance')
    for day, minimum in HISTORICAL_MINIMUMS.items():
        row = await collection.find_one({'_id': 'day:' + day})
        if row is None or type(row.get('calls')) is not int or row['calls'] < minimum:
            raise ValueError('Shared allowance history missing or reset')
    day = datetime.now(UTC).date().isoformat()
    row = await collection.find_one({'_id': 'day:' + day})
    used = (row or {}).get('calls', 0)
    if type(used) is not int or not 0 <= used <= 40 or used + required > 40:
        raise ValueError('Full remaining arm does not fit current shared daily allowance')
    return {'day': day, 'used': used, 'required': required, 'daily_limit': 40,
            'cohort_reservation': False}


async def execute(seal_path, seal_hash, arm, output, *, allow_model=False):
    sealed = verify_seal(seal_path, seal_hash)
    if arm not in ARMS or (arm != 'deterministic' and not allow_model):
        raise ValueError('Selected candidate requires explicit execution authorization')
    # All output setup precedes possible admissions; never overwrite/retry an old arm.
    output.mkdir(parents=True, exist_ok=False)
    initial = dict(seal_sha256=seal_hash, arm=arm, started_at=datetime.now(UTC).isoformat(),
                   acceptance='not_assessed', cases=[{'id': c['id'], 'status': 'not_run'} for c in sealed['fixtures']])
    exclusive_json(output / 'initial.json', initial)
    from motor.motor_asyncio import AsyncIOMotorClient

    from scripts.research_comparison_transport import exercise
    from scripts.research_eval_metrics import measured_bridge, usage_evidence
    from services.agent.codex_model import CodexModel
    from services.agent.repository import AgentRepository
    data = AsyncIOMotorClient('mongodb://127.0.0.1:27017', serverSelectionTimeoutMS=3000, tz_aware=True)
    shared = AsyncIOMotorClient(USAGE_URI, serverSelectionTimeoutMS=3000, tz_aware=True)
    database = data['research_comparison_' + uuid.uuid4().hex]
    collection = shared[USAGE_DB]['agent_oauth_usage']
    results = initial['cases']
    try:
        if await database.list_collection_names():
            raise ValueError('New isolated comparison store is unexpectedly nonempty')
        repository = AgentRepository(database)
        await repository.initialize()
        exclusive_json(output / 'store.json', {'database': database.name, 'uri': 'mongodb://127.0.0.1:27017'})
        candidate = arm != 'deterministic'
        settings = sealed['settings'].get(arm)
        if candidate:
            exclusive_json(output / 'quota-before.json', await quota_preflight(collection, 32))
            verified = await CodexModel(repository, collection).validate_settings(settings)
            if verified != settings:
                raise ValueError('Candidate settings changed')
        # Durable claim prevents a second output directory from repeating this arm.
        # The claim is deliberately retained after failure or process interruption.
        await data['research_comparison_registry']['arms'].insert_one({
            '_id': cohort_identity(sealed['fixtures']) + ':' + arm, 'output': str(output.resolve()),
            'started_at': datetime.now(UTC), 'database': database.name})
        proposal = read_reference(sealed['artifacts']['proposal'])
        for index, ref in enumerate(sealed['fixtures']):
            verify_seal(seal_path, seal_hash)
            if candidate:
                await quota_preflight(collection, 32 - index)
            case = proposal['cases'][index]
            expected = 422 if case['expected']['model_route']['inexpensive'] == 'no_model_before_validation' else 200
            def sink(value, case_id=ref['id']):
                with (output / (case_id + '.trace.jsonl')).open('ab') as stream:
                    stream.write(json.dumps(value, allow_nan=False).encode() + b'\n')
                    stream.flush()
                    os.fsync(stream.fileno())
            def admission_sink(value, case_id=ref['id']):
                exclusive_json(output / (case_id + '.' + value['stage'] + '.json'), value)
            factory = (lambda trace: CodexModel(repository, collection, bridge_factory=measured_bridge(trace))) if candidate else None
            results[index] = {'id': ref['id'], 'status': 'started_outcome_unknown'}
            exclusive_json(output / (ref['id'] + '.started.json'), results[index])
            result = await exercise(read_reference(ref), repository, expected_status=expected,
                                    model_factory=factory, trace_sink=sink, owner_settings=settings, admission_sink=admission_sink)
            saved = result.get('saved_turn')
            if candidate and saved:
                private = await repository.turns.find_one({'turn_id': saved['turn_id']})
                if private is None:
                    raise ValueError('Saved turn is absent from owned storage')
                result['usage'] = await usage_evidence(collection, private['owner'], saved['turn_id'])
            maximum = 0 if not candidate else case['expected']['model_route']['maximum_app_model_entries_per_candidate']
            if (result['trace']['model_invocations'] is None or result['trace']['model_invocations'] > maximum
                    or result['trace']['managed_turn_start_attempts'] > maximum):
                result['errors'].append('Actual model entries exceeded the frozen route bound')
            result['status'] = 'failed' if result['errors'] else 'executed_not_graded'
            exclusive_json(output / (ref['id'] + '.json'), result)
            results[index] = {'id': ref['id'], 'status': result['status'], 'result': reference(output / (ref['id'] + '.json'))}
            if result['errors']:
                raise ValueError('Case failed; remaining cases retained as not_run, no automatic retry')
    except BaseException as exc:
        exclusive_json(output / 'failure.json', {'type': type(exc).__name__, 'message': str(exc),
                                                 'cases': results, 'acceptance': 'incomplete'})
        raise
    finally:
        data.close()
        shared.close()
        exclusive_json(output / 'final.json', {'cases': results, 'acceptance': 'not_assessed',
                         'complete_execution': all(r['status'] == 'executed_not_graded' for r in results),
                         'finished_at': datetime.now(UTC).isoformat()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prep = commands.add_parser('prepare')
    for name in ('proposal', 'bundle', 'oracle', 'grading', 'review', 'authority', 'output'):
        prep.add_argument('--' + name, type=Path, required=True)
    prep.add_argument('--seal', action='store_true')
    run = commands.add_parser('run')
    run.add_argument('--seal', type=Path, required=True)
    run.add_argument('--seal-sha256', required=True)
    run.add_argument('--arm', choices=ARMS, required=True)
    run.add_argument('--output', type=Path, required=True)
    run.add_argument('--allow-model', action='store_true')
    args = parser.parse_args()
    if args.command == 'prepare':
        prepared = prepare(args.proposal, args.bundle, args.oracle, args.grading, args.review, args.authority)
        if args.seal:
            seal(prepared, args.output)
        else:
            exclusive_json(args.output, prepared)
        print(json.dumps({'status': prepared['status'], 'blockers': prepared['blockers'], 'model_calls': 0}))
    else:
        asyncio.run(execute(args.seal, args.seal_sha256, args.arm, args.output, allow_model=args.allow_model))


if __name__ == '__main__':
    main()

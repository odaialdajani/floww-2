"""Run the fixed14 deterministic critical checks without provider/model calls.

Uses a new isolated local durable store for race/interruption recipes. The32
functional questions are not executed. A passing receipt is not browser, live
model, production backup, or research-usefulness acceptance.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import json
import os
import re
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from scripts.research_comparison_run import ROOT, exclusive_json, read_json, reference, source_identity

PROPOSAL = ROOT / '.planning/eval/research-fresh-comparison-proposal-20260926-v3.json'
TEST_FILE = ROOT / 'backend/tests/agent/test_comparison_critical.py'


async def crash_child(name, boundary):
    if not re.fullmatch('research_critical_crash_[a-f0-9]{32}', name):
        raise ValueError('Only a new private critical-check store is allowed')
    if boundary not in {'reserved_before_dispatch', 'local_dispatch_signal'}:
        raise ValueError('Unknown owned interruption boundary')
    from motor.motor_asyncio import AsyncIOMotorClient

    from services.agent.codex_model import OAuthUsage
    from services.agent.contracts import request_spec
    from services.agent.repository import AgentRepository
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27017', serverSelectionTimeoutMS=3000, tz_aware=True)
    database = client[name]
    if await database.list_collection_names():
        raise ValueError('Crash recipe store must be new')
    repo = AgentRepository(database)
    await repo.initialize()
    owner, _ = await repo.session()
    body = next(c['body'] for c in read_json(PROPOSAL)['critical_cases'] if c['id'] == 'critical_crash_unknown_dispatch')
    spec = request_spec(body)
    request_id = f'{int(time.time()*1000)}-{uuid.uuid4()}'
    turn, created = await repo.admit(owner, request_id, spec)
    if not created:
        raise ValueError('Expected a new owned interruption case')
    reservation = await OAuthUsage(database.usage).reserve(owner, turn['turn_id'], {'model': 'FIXTURE_ONLY_NO_MODEL'})
    if reservation is None:
        raise ValueError('Isolated fixture reservation failed')
    if boundary == 'local_dispatch_signal':
        await database.dispatch_signals.insert_one({'turn_id': turn['turn_id'],
            'meaning': 'Local durable test signal only; no model method or provider request was entered'})
    await database.critical_probe.insert_one({'_id': 'controlled-crash', 'owner': owner,
        'turn_id': turn['turn_id'], 'request_id': request_id, 'spec': spec,
        'reservation': list(reservation), 'boundary': boundary})
    # All preceding writes are acknowledged. Abruptly end ONLY this new helper
    # process without service/client close or Python finally/atexit cleanup.
    os._exit(73)


class Receipts:
    def __init__(self, ids):
        self.ids = ids
        self.reports = []

    def pytest_runtest_logreport(self, report):
        self.reports.append({'nodeid': report.nodeid, 'when': report.when, 'outcome': report.outcome,
                             'duration': report.duration, 'properties': dict(report.user_properties)})

    def cases(self):
        result = []
        for case_id in self.ids:
            reports = [r for r in self.reports if ('test_' + case_id) in r['nodeid']
                       or ('[' + case_id) in r['nodeid']]
            calls = [r for r in reports if r['when'] == 'call']
            expected = 4 if case_id == 'critical_cancel_late_worker' else 1
            passed = len(calls) == expected and all(r['outcome'] == 'passed' for r in reports)
            result.append({'id': case_id, 'status': 'passed' if passed else 'failed_or_not_run',
                           'expected_variants': expected, 'reports': reports})
        return result


def verify(output):
    import pytest
    output.mkdir(parents=True, exist_ok=False)
    before = source_identity(ROOT)
    proposal_ref = reference(PROPOSAL)
    ids = [c['id'] for c in read_json(PROPOSAL)['critical_cases']]
    if len(ids) != 14 or len(set(ids)) != 14:
        raise ValueError('Expected14unique critical cases')
    exclusive_json(output / 'initial.json', {'proposal': proposal_ref, 'source_files': before,
        'cases': [{'id': i, 'status': 'not_run'} for i in ids]})
    plugin = Receipts(ids)
    log = io.StringIO()
    with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        code = pytest.main([str(TEST_FILE), '-q', '--disable-warnings'], plugins=[plugin])
    (output / 'pytest.log').write_text(log.getvalue(), encoding='utf-8')
    unchanged = before == source_identity(ROOT) and proposal_ref == reference(PROPOSAL)
    cases = plugin.cases()
    receipt = {'status': 'passed' if code == 0 and unchanged and all(c['status'] == 'passed' for c in cases) else 'failed',
        'proposal_sha256': proposal_ref['sha256'], 'source_files': before, 'source_unchanged': unchanged,
        'test_source': reference(TEST_FILE), 'python': reference(Path(sys.executable)), 'python_version': sys.version,
        'executed_at': datetime.now(UTC).isoformat(), 'pytest_exit_code': int(code), 'cases': cases,
        'functional_comparison_cases_executed': 0, 'real_model_calls': 0, 'provider_calls': 0,
        'fixture_model_entries': sum(r['properties'].get('fixture_model_entries', 0) for r in plugin.reports if r['when'] == 'call'),
        'fixture_model_entries_expected': 3, 'browser_first_display': None,
        'limits': ['Critical fixtures are synthetic; they are not usefulness acceptance',
                   'Local dispatch signal is a controlled uncertainty boundary, not an upstream model call',
                   'Owned helper process interruption is not a database crash or production backup/restore',
                   'Actual HTTP event receipt is not browser paint']}
    exclusive_json(output / 'receipt.json', receipt)
    print(json.dumps({'status': receipt['status'], 'cases': len(cases), 'pytest_exit_code': int(code),
                      'source_unchanged': unchanged, 'real_model_calls': 0}))
    return 0 if receipt['status'] == 'passed' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--crash-child')
    parser.add_argument('--boundary')
    args = parser.parse_args()
    if args.crash_child:
        asyncio.run(crash_child(args.crash_child, args.boundary))
    elif args.output:
        raise SystemExit(verify(args.output))
    else:
        parser.error('An output directory is required')


if __name__ == '__main__':
    main()

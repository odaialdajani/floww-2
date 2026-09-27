"""Prepare private input for blind saved-answer rendering; never execute research.

Only the renderer's answers.html is shared with graders. This input and receipt
contain private saved answers and arm identities and must not be shared blind.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from scripts.research_comparison_inputs import digest, json_bytes
from scripts.research_comparison_run import ARMS, exclusive_json, require_ids

LABELS = ('arm_a', 'arm_b', 'arm_c')
STATUSES = {'executed_not_graded', 'failed', 'started_outcome_unknown', 'not_run'}


def export_packet(seal_path, seal_hash, directories):
    observed = {}

    def read(path, expected=None):
        path = path.resolve()
        raw = path.read_bytes()
        sha = digest(raw)
        if expected is not None and sha != expected:
            raise ValueError('Saved artifact identity differs')
        observed[str(path)] = sha
        return json.loads(raw)

    def frozen(ref):
        path = Path(ref['path'])
        if not path.is_absolute():
            raise ValueError('Frozen reference must be absolute')
        return read(path, ref['sha256'])

    sealed = read(seal_path, seal_hash)
    if sealed.get('status') != 'sealed' or sealed.get('blockers'):
        raise ValueError('A completed prospective seal is required')
    assignment = sealed.get('private_blind_assignment', {})
    if set(assignment) != set(LABELS) or sorted(assignment.values()) != sorted(ARMS):
        raise ValueError('Frozen blind assignment is not one-to-one')
    proposal = frozen(sealed['artifacts']['proposal'])
    ids = [c['id'] for c in proposal['cases']]
    if (len(ids) != 32 or len(set(ids)) != 32
            or any(not isinstance(key, str) or not re.fullmatch(r'[a-z0-9_]+', key) for key in ids)):
        raise ValueError('All 32 distinct frozen cases are required')
    require_ids(sealed['fixtures'], ids, 'Sealed inputs')
    specs = sealed.get('request_specs', {})
    if set(specs) != set(ids):
        raise ValueError('Prospective request identities are missing')
    display = sealed.get('expected_display')
    if not isinstance(display, dict) or not display.get('files'):
        raise ValueError('Prospective display identity is missing')
    if set(directories) - set(ARMS):
        raise ValueError('Unknown candidate directory')
    roots = [Path(p).resolve() for p in directories.values()]
    if len(set(roots)) != len(roots):
        raise ValueError('One directory cannot represent two candidates')
    arms = {}
    for arm in ARMS:
        answers = {key: {'status': 'not_run'} for key in ids}
        if arm not in directories:
            arms[arm] = answers
            continue
        folder = Path(directories[arm]).resolve()
        initial = read(folder / 'initial.json')
        if initial.get('arm') != arm or initial.get('seal_sha256') != seal_hash:
            raise ValueError('Candidate directory belongs to another seal or arm')
        require_ids(initial['cases'], ids, 'Initial denominator')
        if any(c.get('status') != 'not_run' for c in initial['cases']):
            raise ValueError('Initial ledger must precede execution')
        final_path = folder / 'final.json'
        final = read(final_path) if final_path.exists() else None
        if final is not None:
            require_ids(final['cases'], ids, 'Final denominator')
            rows = final['cases']
            complete = all(r.get('status') == 'executed_not_graded' for r in rows)
            if final.get('complete_execution') is not complete:
                raise ValueError('Final completion contradicts case outcomes')
        else:
            # Snapshot an incomplete attempt conservatively. Absence of final.json
            # does not prove a process is dead and never authorizes a retry.
            rows = [{'id': key, 'status': 'started_outcome_unknown'
                     if (folder / (key + '.started.json')).exists() else 'not_run'} for key in ids]
        for case, row in zip(proposal['cases'], rows, strict=True):
            status = row.get('status')
            if status not in STATUSES:
                raise ValueError('Unknown saved outcome')
            key = case['id']
            if status == 'not_run' and (folder / (key + '.started.json')).exists():
                raise ValueError('Started attempt cannot be reported as not run')
            result_ref = row.get('result')
            if status == 'executed_not_graded' and result_ref is None:
                raise ValueError('Completed outcome lacks a saved result')
            result = None
            if result_ref is not None:
                result_path = Path(result_ref['path']).resolve()
                if result_path != folder / (key + '.json'):
                    raise ValueError('Result reference escapes its case and candidate')
                result = frozen(result_ref)
                if result.get('id') != key or result.get('status') != status:
                    raise ValueError('Saved result identity or status differs')
            answer = {'status': status}
            if status == 'executed_not_graded':
                if result.get('errors') != []:
                    raise ValueError('Failed checks cannot be exported as completed')
                refusal_expected = case['expected']['model_route']['inexpensive'] == 'no_model_before_validation'
                if refusal_expected:
                    refusal = result.get('refusal')
                    if (result.get('http_status') != 422 or not isinstance(refusal, dict)
                            or 'detail' not in refusal or result.get('saved_turn')):
                        raise ValueError('Expected refusal lacks its actual display message')
                    detail = refusal['detail']
                    # The two frozen refusal cases use a plain visible detail string.
                    if not isinstance(detail, str) or not detail:
                        raise ValueError('Unsupported refusal display; bind actual UI behavior first')
                    # useAgentStream currently discards server detail on failed ask.
                    # Preserve the actual visible limitation, rather than granting
                    # usefulness to text the trader never sees.
                    answer['refusal'] = 'Research request could not start'
                else:
                    turn = result.get('saved_turn')
                    if (result.get('http_status') != 200 or not isinstance(turn, dict)
                            or turn.get('status') != 'completed' or not turn.get('answer')
                            or result.get('refusal')):
                        raise ValueError('Completed answer lacks a completed saved turn')
                    if (result.get('saved_reopen_identical') is not True
                            or result.get('private_history_present') is not True
                            or result.get('other_owner_status') != 404):
                        raise ValueError('Saved answer lacks reopen and privacy evidence')
                    expected_spec = dict(specs[key])
                    if arm != 'deterministic' and not expected_spec.get('price_only'):
                        settings = sealed.get('settings', {}).get(arm)
                        if not settings:
                            raise ValueError('Sealed candidate settings are missing')
                        expected_spec['ai_settings'] = settings
                    if (turn.get('spec') != expected_spec
                            or any(turn.get(field) != expected_spec.get(field)
                                   for field in ('question', 'ticker', 'horizon'))):
                        raise ValueError('Saved answer belongs to another request or selected model')
                    before = read(folder / (key + '.before_request.json'))
                    admitted = read(folder / (key + '.admitted.json'))
                    if (before.get('stage') != 'before_request' or admitted.get('stage') != 'admitted'
                            or not before.get('owner') or not before.get('request_id')
                            or any(before.get(field) != admitted.get(field) for field in ('owner', 'request_id'))
                            or not turn.get('turn_id') or turn['turn_id'] != admitted.get('turn_id')):
                        raise ValueError('Saved answer differs from owned admission evidence')
                    answer['turn'] = turn
            answers[key] = answer
        arms[arm] = answers
    packet = {'mode': 'comparison', 'expected_display': display, 'cases': [
        {'id': c['id'], 'question': c['body']['question'], 'answers': [
            {'label': label, **arms[assignment[label]][c['id']]} for label in LABELS]}
        for c in proposal['cases']]}
    # Detect edits to files read during this snapshot. A later final file belongs
    # to a later export; this incomplete snapshot never earns acceptance.
    for path, sha in observed.items():
        if digest(Path(path).read_bytes()) != sha:
            raise ValueError('Saved artifact changed during export')
    receipt = {'visibility': 'PRIVATE - do not share with blind graders',
               'seal_sha256': seal_hash, 'private_blind_assignment': assignment,
               'observed_files': observed, 'case_count': 32, 'answer_slots': 96,
               'usefulness': 'not_graded', 'first_browser_display': None,
               'packet_sha256': digest(json_bytes(packet)),
               'limits': ['Export is a file snapshot, not process-death proof or retry authorization',
                          'Only rendered answers.html is provided to blind graders',
                          'Failed, interrupted and absent outcomes remain in the denominator']}
    return packet, receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seal', type=Path, required=True)
    parser.add_argument('--seal-sha256', required=True)
    for arm in ARMS:
        parser.add_argument('--' + arm, type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    packet, receipt = export_packet(args.seal, args.seal_sha256,
        {arm: getattr(args, arm) for arm in ARMS if getattr(args, arm) is not None})
    args.output.mkdir(parents=True, exist_ok=False)
    exclusive_json(args.output / 'private-render-input.json', packet)
    exclusive_json(args.output / 'private-export-receipt.json', receipt)
    print(json.dumps({'case_count': 32, 'answer_slots': 96, 'usefulness': 'not_graded', 'model_calls': 0}))


if __name__ == '__main__':
    main()

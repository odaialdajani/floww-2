"""Invented export fixtures only; none of the frozen comparison answers run."""
import copy

import pytest

from scripts.research_comparison_export import export_packet
from scripts.research_comparison_inputs import json_bytes
from scripts.research_comparison_run import reference


@pytest.fixture
def saved(tmp_path):
    def save(path, value):
        path.write_bytes(json_bytes(value))
        return reference(path)
    ids = ['development_' + str(i) for i in range(32)]
    proposal = {'cases': [{'id': key, 'body': {'question': 'Development question ' + key},
                          'expected': {'model_route': {'inexpensive': 'eligible'}}} for key in ids]}
    specs = {key: {'question': 'Development question ' + key, 'ticker': 'SPY', 'horizon': 'all', 'price_only': False} for key in ids}
    seal = {'request_specs': specs, 'status': 'sealed', 'blockers': [], 'fixtures': [{'id': key} for key in ids],
            'artifacts': {'proposal': save(tmp_path / 'proposal.json', proposal)},
            'private_blind_assignment': {'arm_a': 'stronger', 'arm_b': 'deterministic', 'arm_c': 'inexpensive'},
            'expected_display': {'files': {'development': 'not-a-real-display'}}}
    seal_path = tmp_path / 'seal.json'
    seal_ref = save(seal_path, seal)
    directory = tmp_path / 'deterministic'
    directory.mkdir()
    rows = [{'id': key, 'status': 'not_run'} for key in ids]
    save(directory / 'initial.json', {'arm': 'deterministic', 'seal_sha256': seal_ref['sha256'], 'cases': rows})
    save(directory / (ids[0] + '.before_request.json'), {'stage': 'before_request', 'owner': 'dev-owner', 'request_id': 'dev-request'})
    save(directory / (ids[0] + '.admitted.json'), {'stage': 'admitted', 'owner': 'dev-owner', 'request_id': 'dev-request', 'turn_id': 'dev-turn'})
    result = {'id': ids[0], 'status': 'executed_not_graded', 'errors': [], 'http_status': 200,
              'saved_turn': {'spec': specs[ids[0]], 'question': specs[ids[0]]['question'], 'horizon': 'all', 'turn_id': 'dev-turn', 'status': 'completed', 'ticker': 'SPY', 'answer': {'summary': 'Development only'}},
              'saved_reopen_identical': True, 'private_history_present': True, 'other_owner_status': 404}
    save(directory / (ids[0] + '.started.json'), {'id': ids[0], 'status': 'started_outcome_unknown'})
    ref = save(directory / (ids[0] + '.json'), result)
    final = {'complete_execution': False, 'cases': copy.deepcopy(rows)}
    final['cases'][0] = {'id': ids[0], 'status': 'executed_not_graded', 'result': ref}
    save(directory / 'final.json', final)
    return tmp_path, seal_path, seal_ref['sha256'], directory, save, result, final


def export(saved):
    _, path, sha, directory, *_ = saved
    return export_packet(path, sha, {'deterministic': directory})


def test_frozen_assignment_and_all_96_slots_preserved(saved):
    packet, receipt = export(saved)
    assert len(packet['cases']) == 32
    assert sum(len(c['answers']) for c in packet['cases']) == 96
    first = packet['cases'][0]['answers']
    assert [a['label'] for a in first] == ['arm_a', 'arm_b', 'arm_c']
    assert first[0]['status'] == first[2]['status'] == 'not_run'
    assert first[1]['turn']['answer']['summary'] == 'Development only'
    assert receipt['usefulness'] == 'not_graded'
    assert receipt['first_browser_display'] is None
    assert receipt['visibility'].startswith('PRIVATE')


def test_changed_result_cannot_be_displayed_under_old_identity(saved):
    saved[4](saved[3] / 'development_0.json', dict(saved[5], errors=['changed']))
    with pytest.raises(ValueError, match='identity differs'):
        export(saved)


def test_missing_final_is_conservative_even_if_result_file_exists(saved):
    (saved[3] / 'final.json').unlink()
    packet, _ = export(saved)
    first = packet['cases'][0]['answers'][1]
    assert first == {'label': 'arm_b', 'status': 'started_outcome_unknown'}
    assert all('turn' not in a for c in packet['cases'] for a in c['answers'])


@pytest.mark.parametrize('mutation', ['missing', 'completion', 'started', 'outside', 'status', 'errors', 'privacy'])
def test_malformed_or_misleading_results_refused(saved, mutation):
    root, _, _, directory, save, result, final = saved
    if mutation == 'missing':
        final['cases'].pop()
    elif mutation == 'completion':
        final['complete_execution'] = True
    elif mutation == 'started':
        final['cases'][0] = {'id': 'development_0', 'status': 'not_run'}
    elif mutation == 'outside':
        final['cases'][0]['result'] = save(root / 'foreign.json', result)
    else:
        if mutation == 'status':
            result['status'] = 'failed'
        elif mutation == 'errors':
            result['errors'] = ['actual failure']
        else:
            result['other_owner_status'] = 200
        final['cases'][0]['result'] = save(directory / 'development_0.json', result)
    save(directory / 'final.json', final)
    with pytest.raises(ValueError):
        export(saved)


def test_wrong_arm_and_reused_directory_refused(saved):
    with pytest.raises(ValueError, match='another seal or arm'):
        export_packet(saved[1], saved[2], {'stronger': saved[3]})
    with pytest.raises(ValueError, match='two candidates'):
        export_packet(saved[1], saved[2], {'stronger': saved[3], 'deterministic': saved[3]})


def test_failed_outcome_stays_failed_without_success_content(saved):
    _, _, _, directory, save, result, final = saved
    result['status'] = 'failed'
    result['errors'] = ['actual fixture error']
    final['cases'][0]['status'] = 'failed'
    final['cases'][0]['result'] = save(directory / 'development_0.json', result)
    save(directory / 'final.json', final)
    packet, _ = export(saved)
    assert packet['cases'][0]['answers'][1] == {'label': 'arm_b', 'status': 'failed'}


def test_refusal_preserves_actual_response_for_shared_ui_message_function(saved):
    import json
    root, seal_path, _, directory, save, result, final = saved
    proposal = json.loads((root / 'proposal.json').read_bytes())
    proposal['cases'][0]['expected']['model_route']['inexpensive'] = 'no_model_before_validation'
    seal = json.loads(seal_path.read_bytes())
    seal['artifacts']['proposal'] = save(root / 'proposal.json', proposal)
    seal_hash = save(seal_path, seal)['sha256']
    initial = json.loads((directory / 'initial.json').read_bytes())
    initial['seal_sha256'] = seal_hash
    save(directory / 'initial.json', initial)
    result.pop('saved_turn')
    result.update(http_status=422, refusal={'detail': 'Private server restriction explanation'})
    final['cases'][0]['result'] = save(directory / 'development_0.json', result)
    save(directory / 'final.json', final)
    packet, _ = export_packet(seal_path, seal_hash, {'deterministic': directory})
    assert packet['cases'][0]['answers'][1]['refusal'] == {
        'status': 422, 'body': {'detail': 'Private server restriction explanation'}}


@pytest.mark.parametrize('field,value', [('question', 'Foreign question'), ('turn_id', 'foreign-turn'),
                                         ('spec', {'question': 'foreign'}), ('ticker', 'QQQ'), ('horizon', 'week')])
def test_foreign_saved_turn_cannot_borrow_a_valid_result_wrapper(saved, field, value):
    _, _, _, directory, save, result, final = saved
    result['saved_turn'][field] = value
    final['cases'][0]['result'] = save(directory / 'development_0.json', result)
    save(directory / 'final.json', final)
    with pytest.raises(ValueError, match='another request|admission evidence'):
        export(saved)


def test_candidate_settings_cannot_be_substituted(saved):
    import json
    _, seal_path, _, directory, save, result, final = saved
    seal = json.loads(seal_path.read_bytes())
    seal['settings'] = {'stronger': {'model': 'EXPECTED_DEVELOPMENT', 'effort': 'medium', 'speed': 'default'}}
    sha = save(seal_path, seal)['sha256']
    initial = json.loads((directory / 'initial.json').read_bytes())
    initial.update(arm='stronger', seal_sha256=sha)
    save(directory / 'initial.json', initial)
    result['saved_turn']['spec']['ai_settings'] = {'model': 'FOREIGN_DEVELOPMENT', 'effort': 'medium', 'speed': 'default'}
    final['cases'][0]['result'] = save(directory / 'development_0.json', result)
    save(directory / 'final.json', final)
    with pytest.raises(ValueError, match='selected model'):
        export_packet(seal_path, sha, {'stronger': directory})

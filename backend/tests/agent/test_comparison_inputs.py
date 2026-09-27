"""Input preparation must preserve evidence and never imply execution readiness."""
import copy
import json
from pathlib import Path

import pytest

from scripts.research_comparison_inputs import (
    archive_inputs,
    build_bundle,
    chain_oracle,
    check_clock,
    history_inputs,
    prepare_case,
    synthetic_chain,
    verify_sources,
)

ROOT = Path(__file__).resolve().parents[3]
PROPOSAL = ROOT / '.planning/eval/research-fresh-comparison-proposal-20260926.json'


def unit_proposal(tmp_path):
    # Unit fixtures bind immutable raw captures only. The actual preparation
    # command separately verifies every dated proposal reference. Routine
    # application/doc edits must not break these raw-materialization tests.
    proposal = json.loads(PROPOSAL.read_text())
    proposal['source_catalog'] = [ref for ref in proposal['source_catalog']
                                  if ref['id'] in {'archive_chains', 'archive_aapl', 'archive_maps'}]
    path = tmp_path / 'unit-proposal.json'
    path.write_text(json.dumps(proposal))
    return path



def test_source_drift_and_escape_refused(tmp_path):
    (tmp_path / 'source.json').write_text('{}')
    with pytest.raises(ValueError, match='changed'):
        verify_sources(tmp_path, [{'id': 'a', 'path': 'source.json', 'sha256': '0' * 64}])
    with pytest.raises(ValueError, match='outside'):
        verify_sources(tmp_path, [{'id': 'a', 'path': '../source.json', 'sha256': '0' * 64}])


def test_archive_extract_is_detached_and_preserves_missing_time():
    raw = {'ticker': 'SPY', 'spot': 100, 'event_time': None, 'contracts': []}
    source = {'archive_chains': {'sources': {'SPY': {'source': {'raw_public_chain': raw}}}}}
    result = archive_inputs(['SPY'], source)
    result['SPY']['spot'] = 200
    assert raw['spot'] == 100
    assert result['SPY']['event_time'] is None
    with pytest.raises(ValueError, match='ticker'):
        archive_inputs(['QQQ'], source)


def test_synthetic_oracle_distinguishes_zero_missing_and_unpaired_iv():
    raw = synthetic_chain('DIA', {'variant': 'zero_vs_null_oi', 'call_oi': 0, 'put_oi': None})
    result = chain_oracle(raw)
    assert result['zero_open_interest'] == 1
    assert result['missing_open_interest'] == 1
    assert result['captured_contracts'] == 2
    assert raw['source'] == 'SYNTHETIC_CONTRACT_TEST'
    unpaired = synthetic_chain('QQQ', {'variant': 'put_iv_missing', 'put_iv': None})
    assert unpaired['contracts'][1]['iv'] is None
    assert unpaired['contracts'][0]['iv'] == .20


def test_undeclared_synthetic_variant_refused():
    with pytest.raises(ValueError, match='Unsupported'):
        synthetic_chain('SPY', {'variant': 'guess_missing_source_time'})
    with pytest.raises(ValueError, match='Unsupported'):
        synthetic_chain('SPY', {'unlisted_override': 1})


def test_real_proposal_keeps_every_case_and_pending_evidence(tmp_path):
    proposal = json.loads(PROPOSAL.read_text())
    original = copy.deepcopy(proposal)
    output = tmp_path / 'prepared'
    report = build_bundle(ROOT, unit_proposal(tmp_path), output)
    assert proposal == original
    assert len(report['cases']) == 32
    assert report['execution_ready'] is False
    assert report['model_calls'] == 0
    by_id = {c['id']: c for c in report['cases']}
    assert by_id['proposed_real_fresh_alerts']['raw_inputs_present'] is False
    assert by_id['owned_price_change']['raw_inputs_present'] is True
    assert by_id['owned_price_change']['history_store_proof'] is None
    missing = json.loads((output / by_id['map_missing_cell_total']['fixture']['path']).read_text())
    assert missing['maps']['SPY']['grid']['grid']['2026-10-09']['100'] is None
    assert missing['oracles']['map']['cumulative'] == [3, None, None]
    zero = json.loads((output / by_id['map_measured_zero']['fixture']['path']).read_text())
    assert zero['oracles']['map']['selected_value'] == 0
    history = json.loads((output / by_id['owned_price_change']['fixture']['path']).read_text())
    assert history['history']['IWM']['prior_raw']['spot'] == 100
    assert history['chains']['IWM']['spot'] == 102
    assert history['history']['IWM']['same_owner'] is True
    assert all(c['route_proof'] is None for c in report['cases'])
    with pytest.raises(FileExistsError):
        build_bundle(ROOT, unit_proposal(tmp_path), output)


def test_history_default_has_the_declared_change_and_later_receipt():
    chains = {'SPY': synthetic_chain('SPY', {})}
    history = history_inputs(chains, {'variant': 'matching_coverage'})
    assert chains['SPY']['spot'] == 102
    assert history['SPY']['prior_raw']['spot'] == 100
    assert history['SPY']['raw_price_difference'] == 2
    assert history['SPY']['prior_raw']['fetched_at'] > history['SPY']['prior_raw']['event_time']


def test_future_observation_and_naive_clock_refused():
    with pytest.raises(ValueError, match='exceeds'):
        check_clock({'contracts': [{'iv_event_time': '2026-09-28T14:31:00Z'}]}, '2026-09-28T14:30:00Z')
    with pytest.raises(ValueError, match='timezone'):
        check_clock({}, '2026-09-28T14:30:00')


def test_changed_history_selection_adds_a_distinct_expiry():
    chains = {'SPY': synthetic_chain('SPY', {})}
    history = history_inputs(chains, {'variant': 'different_coverage_same_horizon'})
    prior = history['SPY']['prior_raw']
    assert set(prior['expiries']) != set(chains['SPY']['expiries'])
    assert {c['expiry'] for c in prior['contracts']} == set(prior['expiries'])
    assert chains['SPY']['expiries'] == ['2026-10-02']


def test_late_nonfinite_input_leaves_no_partial_bundle(tmp_path):
    proposal = json.loads(unit_proposal(tmp_path).read_text())
    late = next(c for c in proposal['cases'] if c['id'] == 'source_label_instructions')
    late['recipes'][0]['parameters']['spot'] = float('nan')
    changed = tmp_path / 'draft.json'
    changed.write_text(json.dumps(proposal))
    target = tmp_path / 'result'
    with pytest.raises(ValueError):
        build_bundle(ROOT, changed, target)
    assert not target.exists()


@pytest.mark.parametrize('name', ['manifest', 'con', 'nul', 'aux', 'prn', 'com1', 'lpt9'])
def test_reserved_case_names_refuse_without_creating_output(tmp_path, name):
    proposal = json.loads(unit_proposal(tmp_path).read_text())
    proposal['cases'][0]['id'] = name
    changed = tmp_path / 'draft.json'
    changed.write_text(json.dumps(proposal))
    output = tmp_path / 'result'
    with pytest.raises(ValueError, match='reserved'):
        build_bundle(ROOT, changed, output)
    assert not output.exists()


def test_prospective_revision_prepares_all_inputs_but_not_acceptance(tmp_path):
    path = ROOT / '.planning/eval/research-fresh-comparison-proposal-20260926-v3.json'
    proposal = json.loads(path.read_text())
    proposal['source_catalog'] = [r for r in proposal['source_catalog'] if r['id'] in {'archive_chains', 'archive_aapl', 'archive_maps'}]
    unit = tmp_path / 'revision.json'
    unit.write_text(json.dumps(proposal))
    target = tmp_path / 'revised'
    report = build_bundle(ROOT, unit, target)
    assert len(report['cases']) == 32 and all(c['raw_inputs_present'] for c in report['cases'])
    assert report['execution_ready'] is False
    bracket = json.loads((target / 'synthetic_bracketing_levels.json').read_text())
    assert [c['strike'] for c in bracket['chains']['AAPL']['contracts']] == [95, 105]
    mapped = json.loads((target / 'synthetic_cached_map_price.json').read_text())
    assert mapped['chains']['SPY']['spot'] == 103
    assert mapped['maps']['SPY']['spot'] == 100
    assert mapped['maps']['SPY']['gamma_flip']['gamma_flip'] == 101
    assert len(proposal['unproven_real_positive_coverage']) == 4


@pytest.mark.parametrize('field,value', [('mapStrikes', [100]), ('mapExpiries', ['2026-10-02']), ('selectedStrike', 110)])
def test_explicit_map_axes_and_selection_must_match(field, value):
    path = ROOT / '.planning/eval/research-fresh-comparison-proposal-20260926-v3.json'
    proposal = json.loads(path.read_text())
    case = next(c for c in proposal['cases'] if c['id'] == 'synthetic_cached_map_price')
    case['body']['screen'][field] = value
    with pytest.raises(ValueError, match='axes or selection'):
        prepare_case(case, {})

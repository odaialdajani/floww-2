"""Preseal raw arithmetic checks; no research answers or model calls."""
import json
from datetime import datetime
from pathlib import Path

import pytest

from scripts.research_comparison_alerts import AlertFixture
from scripts.research_comparison_inputs import prepare_case
from services.agent.contracts import request_spec
from services.agent.read_budget import ReadBudget, budget_scope
from services.agent.reads import ResearchReads

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.asyncio
@pytest.mark.parametrize('identity,expected', [
    ('synthetic_bracketing_levels', {'Nearest exposure level below': 95, 'Nearest exposure level above': 105,
                                    'Total estimated gamma exposure': 400}),
    ('synthetic_move_not_straddle', {'At-the-money implied volatility': .22, 'Implied move estimate': 1.89,
                                    'Implied move lower bound': 98.11, 'Implied move upper bound': 101.89}),
    ('synthetic_cached_map_price', {'Underlying price': 103, 'Cached map price': 100, 'Displayed flip': 101,
                                   'Selected display cell': 2}),
    ('synthetic_aligned_positive_flow', {'Signed alert reading': .7}),
])
async def test_actual_reads_match_independent_positive_operands(identity, expected):
    proposal = json.loads((ROOT / '.planning/eval/research-fresh-comparison-proposal-20260926-v3.json').read_text())
    case = next(c for c in proposal['cases'] if c['id'] == identity)
    prepared = prepare_case(case, {})
    spec = request_spec(case['body'])
    assert len(spec['tickers']) == 1
    ticker = spec['tickers'][0]
    with AlertFixture(prepared) as alerts:
        reads = ResearchReads(lambda t, _: prepared['chains'].get(t),
                              lambda t, _: prepared['maps'].get(t), alerts.read)
        budget = ReadBudget()
        with budget_scope(budget, spec):
            snapshot = await reads.snapshot(ticker, spec['horizon'],
                now=datetime.fromisoformat(case['clock']['at'].replace('Z', '+00:00')),
                screen=case['body']['screen'],
                selected_expiry=(spec.get('question_scope') or {}).get('selected_expiry') or case['body']['screen'].get('selectedExpiry'))
        by_name = {fact['metric']: fact for fact in snapshot['facts']}
        for metric, value in expected.items():
            assert metric in by_name, (metric, snapshot['gaps'])
            assert by_name[metric]['value'] == pytest.approx(value)
            assert by_name[metric]['status'] == 'ok'
        if identity == 'synthetic_aligned_positive_flow':
            assert alerts.receipts[-1]['status'] == 'ok'
            assert alerts.receipts[-1]['rows'] == 2
        budget.close()

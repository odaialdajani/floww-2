"""Actual isolated alert writes/queries, with explicit evidence clocks."""
import json
import socket
from pathlib import Path

import duckdb
import pytest

from scripts.research_comparison_alerts import AlertFixture


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError('Offline alert fixture attempted network')
    monkeypatch.setattr(socket.socket, 'connect', refuse)


def item(mode):
    return {'clock': {'at': '2026-09-28T14:30:00Z'}, 'chains': {},
            'alerts': {'mode': mode, 'parameters': {}}}


def test_empty_query_is_successful_only_in_its_owned_store():
    with AlertFixture(item('controlled_empty_alerts')) as fixture:
        assert fixture.read('IWM') == []
        assert fixture.receipts[-1]['status'] == 'ok'
        assert fixture.receipts[-1]['rows'] == 0
        assert fixture.receipts[-1]['params'] == ['IWM', '2026-09-21']
        assert fixture.label == 'CONTROLLED_EMPTY_STORE'


def test_missing_table_records_error_not_empty():
    with AlertFixture(item('controlled_alert_error')) as fixture:
        with pytest.raises(duckdb.CatalogException):
            fixture.read('DIA')
        assert fixture.receipts[-1]['status'] == 'error'
        assert fixture.receipts[-1]['rows'] is None


def test_synthetic_direction_uses_actual_saved_rows_and_source_times():
    value = item('synthetic_alerts_positive')
    value['chains'] = {'SPY': {}}
    with AlertFixture(value) as fixture:
        rows = fixture.read('SPY')
        assert len(rows) == 2
        assert sorted(r['conviction'] for r in rows) == [40, 80]
        assert {r['bias'].lower() for r in rows} == {'bullish', 'bearish'}
        assert {r['asof_ts'].isoformat() for r in rows} == {'2026-09-28T14:29:30+00:00', '2026-09-28T14:29:40+00:00'}
        assert fixture.receipts[-1]['status'] == 'ok'
        assert fixture.label == 'SYNTHETIC_CONTRACT_TEST'


def test_real_chain_derived_alerts_keep_unknown_source_freshness():
    root = Path(__file__).resolve().parents[3]
    raw = json.loads((root / '.planning/eval/oauth-heldout-v2-sources.json').read_text())['sources']['QQQ']['source']['raw_public_chain']
    value = item('derived_alerts_unknown')
    value['clock']['at'] = '2026-09-11T22:52:00Z'
    value['chains'] = {'QQQ': raw}
    with AlertFixture(value) as fixture:
        rows = fixture.read('QQQ')
        assert rows
        assert all(row['asof_ts'] is None for row in rows)
        assert all(row['computed_at'] is not None for row in rows)
        assert fixture.label == 'DERIVED_FROM_RECORDED_PUBLIC_CHAINS'


def test_revised_positive_rows_keep_the_reviewed_fields_and_clock():
    root = Path(__file__).resolve().parents[3]
    proposal = json.loads((root / '.planning/eval/research-fresh-comparison-proposal-20260926-v3.json').read_text())
    case = next(c for c in proposal['cases'] if c['id'] == 'synthetic_aligned_positive_flow')
    value = item('synthetic_alerts_positive')
    value['chains'] = {'QQQ': {}}
    value['alerts']['parameters'] = case['recipes'][1]['parameters']
    with AlertFixture(value) as fixture:
        rows = fixture.read('QQQ')
        assert len(rows) == 2
        assert all(row['bias'] == 'BULLISH' for row in rows)
        assert sum(row['conviction'] / 100 for row in rows) / 2 == .7
        assert all(row['computed_at'].isoformat() == '2026-09-28T14:29:50+00:00' for row in rows)
        assert fixture.receipts[-1]['params'] == ['QQQ', '2026-09-21']


def test_clock_and_connection_close_after_failed_population():
    from services import flow_alerts, research_data_seam
    before = (flow_alerts.datetime, research_data_seam.datetime)
    value = item('synthetic_alerts_positive')
    value['chains'] = {'QQQ': {}}
    value['alerts']['parameters'] = {'variant': 'unsupported'}
    fixture = AlertFixture(value)
    with pytest.raises(ValueError, match='variant'):
        with fixture:
            pass
    assert fixture.engine is None
    assert (flow_alerts.datetime, research_data_seam.datetime) == before
    with pytest.raises(RuntimeError, match='not open'):
        fixture.read('QQQ')


@pytest.mark.parametrize('mutation', ['future_source', 'future_created', 'duplicate', 'wrong_direction', 'too_large', 'unknown_parameter', 'empty_scope', 'fractional_conviction', 'utc_creation'])
def test_invalid_positive_rows_refuse_before_any_receipt(mutation):
    root = Path(__file__).resolve().parents[3]
    proposal = json.loads((root / '.planning/eval/research-fresh-comparison-proposal-20260926-v3.json').read_text())
    case = next(c for c in proposal['cases'] if c['id'] == 'synthetic_aligned_positive_flow')
    value = item('synthetic_alerts_positive')
    value['chains'] = {'QQQ': {}}
    value['alerts']['parameters'] = case['recipes'][1]['parameters']
    rows = value['alerts']['parameters']['rows']
    if mutation == 'future_source':
        rows[0]['context']['source_event_time'] = '2026-09-28T14:31:00Z'
    elif mutation == 'future_created':
        rows[0]['asof'] = '2026-09-28T10:31:00-04:00'
    elif mutation == 'duplicate':
        rows[1]['key'] = rows[0]['key']
    elif mutation == 'wrong_direction':
        rows[1]['bias'] = 'BEARISH'
    elif mutation == 'too_large':
        rows[0]['conviction'] = 101
    elif mutation == 'fractional_conviction':
        rows[0]['conviction'] = 80.4
    elif mutation == 'utc_creation':
        rows[0]['asof'] = '2026-09-28T14:29:50Z'
    elif mutation == 'unknown_parameter':
        value['alerts']['parameters']['invented'] = True
    else:
        value['chains'] = {}
    with pytest.raises(ValueError):
        with AlertFixture(value):
            pass

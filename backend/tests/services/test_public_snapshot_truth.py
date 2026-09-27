import json
from datetime import UTC, datetime

from services import flow_alerts as alerts
from services import public_scanner as scanner
from services.duckdb_engine import DuckDBEngine

NOW = datetime(2026, 9, 25, 14, tzinfo=UTC).timestamp()


def snapshot(mid=2):
    contract = dict(osi='TEST261016C00100000', type='call', strike=100, expiry='2026-10-16', volume=1000, oi=100,
                    bid=mid-0.1, ask=mid+0.1, mid=mid, last=mid+0.1, bid_timestamp=NOW, ask_timestamp=NOW,
                    last_timestamp=NOW, iv=0.3, delta=0.5)
    rows, extras = scanner.unusual_rows_from_chain(dict(ticker='TEST', spot=100, contracts=[contract]), now=NOW)
    return alerts.apply_quote_truth(alerts.norm_rows(rows), extras)[0], extras


def test_quote_estimate_reprices_without_claiming_executed_money():
    one, first = snapshot(1)
    two, second = snapshot(2)
    assert one['vol'] == two['vol'] == 1000
    assert one['premium'] == 100000 and two['premium'] == 200000
    assert one['premium_truth'] is two['premium_truth'] is False
    assert two['premium_basis'] == 'snapshot_volume_x_quote'
    assert next(iter(second.values()))['last_trade_side'] == 'ASK'


def test_cumulative_snapshot_never_gets_whole_day_side_or_known_side_bonus():
    row, extras = snapshot()
    assert alerts.infer_side_bias(row) == ('FLOW', None)
    assert row['last_trade_side'] == 'ASK'
    assert 'signed_side' not in row and 'nbbo_side' not in row
    contaminated = {**row, 'signed_side':'ASK','nbbo_side':'ASK','sign_method':'quote'}
    assert alerts.infer_side_bias(contaminated) == ('FLOW',None)
    assert alerts.score_conviction(contaminated,{}) == alerts.score_conviction(row,{})
    alert = alerts._mk_alert(row,'WHALE',{'why':'Daily volume found'},{},'2026-09-25T14:00:00Z')
    assert alert['side']=='FLOW' and alert['bias'] is None and alert['key_levels'] is None
    assert 'estimated' in alert['why'] and 'direction is unknown' in alert['why']


def test_saved_alert_retains_snapshot_provenance_and_unknown_direction():
    row, _ = snapshot()
    alert = alerts._mk_alert(row,'WHALE',{}, {},'2026-09-25T14:00:00Z')
    engine= DuckDBEngine(':memory:')
    try:
        alerts.init_flow_alert_tables(engine)
        alerts.persist_alerts(engine,[alert],snapshot_date='2026-09-25')
        saved=engine.query_strict('SELECT side,bias,context_json,key_levels_json FROM flow_alerts_daily')[0]
        context=json.loads(saved['context_json'])
        assert saved['side']=='FLOW' and saved['bias'] is None and saved['key_levels_json'] is None
        assert context['activity_basis']=='cumulative_snapshot'
        assert context['premium_basis']=='snapshot_volume_x_quote' and context['premium_truth'] is False
        alerts.update_moves(engine, {"TEST": 110})
        assert alerts.alert_quality(engine, days=30) == []
        assert alerts.alert_quality_daily(engine, days=30) == []
    finally:
        engine.close()


def test_alternate_daily_volume_source_cannot_infer_direction_without_extras():
    raw=[["TEST","TEST261016C00100000","call",100,"2026-10-16",1000,100,0.3,0.5,100]]
    row=alerts.norm_rows(raw)[0]
    assert row["activity_basis"]=="cumulative_snapshot"
    assert row["premium_basis"]=="snapshot_volume_x_model_price"
    assert alerts.infer_side_bias(row)==("FLOW",None)
    assert alerts._mk_alert(row,"WHALE",{}, {},"2026-09-25T14:00:00Z")["key_levels"] is None

"""Synthetic process-restart proof through the actual engine/record/node seams.

No lifespan, provider request, activation or source-store access. This verifies
engineering durability; it cannot recover missed real-world observations.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = r'''
import json
import os
import socket
import sys

def no_network(*args, **kwargs):
    raise AssertionError('No network in snapshot restart proof')
socket.socket.connect = no_network
socket.create_connection = no_network
from services.duckdb_engine import db
from services.heatmap_history import record_snapshot, recorder_status
from services.price_node_history import build_history, scope_id
from routes.price_history import read_snapshots

db.conn.execute('SET threads=1')
assert recorder_status(db.conn)['durable'] is True
assert os.environ['FLOWW_SOLSTICE_CAPTURE'] == '0'
assert os.environ['FLOWW_ENABLE_LIVE_PUBLIC'] == '0'
payload = {
    'ticker':'SPY', 'spot':100, 'expiries_used':['2026-10-06'],
    'asof':'2026-10-06T14:00:00+00:00',
    'source_received_at':'2026-10-06T14:02:00+00:00',
    'formula_version':'gex.v2', 'exposure_basis':'OI',
    'data_source':'synthetic-restart-fixture',
    'strikes':[{'strike':100,'gex_net':10}],
    'metrics':{'walls':[{'wall_id':'fixture-wall','mid':100,'low':99,'high':101}]},
    'contracts':[{'osi':'SPY261006C00100000','expiry':'2026-10-06',
                  'strike':100,'type':'call','multiplier':100,'oi':0,
                  'gamma':None,'volume':None,'received_at':'2026-10-06T14:02:00+00:00'}],
}
key='SPY:4:day:None:False:True:80'
mode=sys.argv[1]
if mode=='write':
    sid=record_snapshot(db.conn,payload,query_key=key)
    assert sid is not None, 'COMMIT must acknowledge the observation'
    assert db.conn.execute('SELECT count(*) FROM heatmap_snapshots_v2').fetchone()[0]==1
    assert db.conn.execute('SELECT count(*) FROM contract_observations_v2').fetchone()[0]==1
    result={'pid':os.getpid(),'snapshot_id':sid,'committed':True}
else:
    rows=read_snapshots(db,'SPY','2026-10-06T13:45:00+00:00','2026-10-06T14:30:00+00:00')
    assert len(rows)==1
    row=rows[0]
    assert row['asof_ts']==payload['asof']
    assert row['received_at']==payload['source_received_at']
    scope=scope_id(row)
    assert scope==key+'|expiries=2026-10-06|gex.v2|OI'
    clocks=['2026-10-06T14:01:00Z','2026-10-06T14:02:00Z','2026-10-06T14:17:00Z']
    bars=[{'t':t,'o':100,'h':102,'l':99,'c':101,'v':0} for t in clocks]
    result=build_history('SPY',bars,rows,query_key=scope)
    assert [len(f['nodes']) for f in result['frames']]==[0,1,0]
    assert result['candles_with_recorded_nodes']==1
    assert result['frames'][1]['snapshot_id']==row['snapshot_id']
    assert result['frames'][1]['nodes_known_at']=='2026-10-06T14:02:00+00:00'
    assert result['frames'][1]['node_age_seconds']==120
    assert result['node_coverage']['gap_counts']=={'no_prior_observation':1,'observation_too_old':1,'recorded_without_nodes':0}
    wrong=build_history('SPY',bars,rows,query_key=scope+'-other')
    assert wrong['candles_with_recorded_nodes']==0
    quotes=db.conn.execute('SELECT osi,oi,gamma,volume,received_at FROM contract_observations_v2').fetchall()
    assert quotes==[('SPY261006C00100000',0.0,None,None,'2026-10-06T14:02:00+00:00')]
    result={'pid':os.getpid(),'snapshot_id':row['snapshot_id'],'matching_candles':1,
            'gap_counts':result['node_coverage']['gap_counts'],'clocks_preserved':True,
            'physical_contract_rows':len(quotes),'unknowns_preserved':True,'scope_refused':True}
db.close()
print(json.dumps(result))
'''


def test_engine_snapshot_survives_distinct_process_restart_and_node_join(tmp_path):
    store = tmp_path / 'isolated-snapshots.duckdb'
    env = dict(os.environ)
    env.update(DUCKDB_PATH=str(store), PUBLIC_API_KEY='', FLOWW_SOLSTICE_CAPTURE='0',
               FLOWW_RECORDER_WORKER='0', FLOWW_ENABLE_LIVE_PUBLIC='0',
               FLOWW_RANGE_CAPTURE_ENABLED='0', FLOWW_PRICE_PATH_PRODUCER='0',
               TESTING='1', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
    receipts = []
    for mode in ['write', 'read', 'read']:
        run = subprocess.run(
            [sys.executable, '-c', SCRIPT, mode],
            cwd=Path(__file__).resolve().parents[2], env=env,
            capture_output=True, text=True, timeout=60,
            **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}),
        )
        assert run.returncode == 0, run.stdout + run.stderr
        receipts.append(json.loads(run.stdout.splitlines()[-1]))
    assert store.is_file()
    assert len({r['pid'] for r in receipts}) == 3
    assert len({r['snapshot_id'] for r in receipts}) == 1
    assert all(r['matching_candles'] == 1 for r in receipts[1:])

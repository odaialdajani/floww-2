"""Recheck preserved public-market observations against independent joins.

Collection accepts ONLY an isolated copy, never the running source store.
Default mode reopens the bounded evidence in memory and rewrites its report.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import duckdb

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT/'backend'))
from services.price_node_history import build_history, epoch, recorded_nodes, scope_id  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument('--collect', type=Path)
parser.add_argument('--bars', type=Path)
parser.add_argument('--manifest', type=Path)
args = parser.parse_args()
evidence_path = HERE/'history-evidence.json'
if args.collect:
    assert args.bars and args.manifest
    manifest = json.loads(args.manifest.read_text())
    assert args.collect.resolve() == Path(manifest['copy']).resolve()
    assert str(args.collect.resolve()) not in manifest['files'], 'Never open the source store'
    conn = duckdb.connect(str(args.collect), read_only=True)
    cursor = conn.execute("SELECT snapshot_id,ticker,query_key,expiries,formula_version,exposure_basis,asof_ts,received_at,walls_json FROM heatmap_snapshots_v2 WHERE ticker='SPY'")
    columns = [col[0] for col in cursor.description]
    rows = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
    conn.close()
    live = json.loads(args.bars.read_text())
    evidence = {'provenance':manifest,'rows':rows,'live_control':{key:live.get(key) for key in ['prices_received_at','last_candle_at','query_key','recording']},'bars':[{'t':f['time'],'o':f['open'],'h':f['high'],'l':f['low'],'c':f['close'],'v':f.get('volume')} for f in live['frames']]}
    evidence_path.write_text(json.dumps(evidence,separators=(',',':'))+'\n')

raw = evidence_path.read_bytes()
evidence = json.loads(raw)
rows,bars = evidence['rows'],evidence['bars']
known = [(max(epoch(r['asof_ts']),epoch(r['received_at'])),r) for r in rows if epoch(r['asof_ts']) is not None and epoch(r['received_at']) is not None]
scopes = sorted({scope_id(row) for _,row in known})
matched_candles = set()
results=[]
for scope in scopes:
    own=[(at,row) for at,row in known if scope_id(row)==scope]
    oracle={'no_prior_observation':0,'observation_too_old':0,'recorded_without_nodes':0}
    matches=0
    for bar in bars:
        at=epoch(bar['t'])
        candidates=[pair for pair in own if pair[0]<=at]
        if not candidates:
            oracle['no_prior_observation']+=1
            continue
        _,row=max(candidates,key=lambda pair:(epoch(pair[1]['asof_ts']),pair[0],pair[1]['snapshot_id']))
        if at-epoch(row['asof_ts'])>900:
            oracle['observation_too_old']+=1
        elif not recorded_nodes(row):
            oracle['recorded_without_nodes']+=1
        else:
            matches+=1
            matched_candles.add(bar['t'])
    output=build_history('SPY',bars,rows,scope)
    assert output['candles_with_recorded_nodes']==matches
    assert output['node_coverage']['gap_counts']==oracle
    assert matches+sum(oracle.values())==len(bars)
    results.append({'scope':scope,'stored_rows':len(own),'matching_candles':matches,'gap_counts':oracle})

# Independent SQL window join over the preserved raw clocks/identity fields.
# Not the production cursor implementation and not the exhaustive Python loop.
conn=duckdb.connect(':memory:')
conn.execute('CREATE TABLE readings(snapshot_id VARCHAR,query_key VARCHAR,expiries VARCHAR,formula_version VARCHAR,exposure_basis VARCHAR,asof_ts VARCHAR,received_at VARCHAR,walls_json VARCHAR)')
conn.executemany('INSERT INTO readings VALUES (?,?,?,?,?,?,?,?)',[[r[k] for k in ['snapshot_id','query_key','expiries','formula_version','exposure_basis','asof_ts','received_at','walls_json']] for r in rows])
conn.execute('CREATE TABLE candles(candle_at TIMESTAMPTZ)')
conn.executemany('INSERT INTO candles VALUES (?)',[[b['t']] for b in bars])
count=conn.execute("""WITH chosen AS (
 SELECT candles.candle_at, readings.*,
 ROW_NUMBER() OVER (PARTITION BY candles.candle_at,query_key,expiries,formula_version,exposure_basis
 ORDER BY TRY_CAST(asof_ts AS TIMESTAMPTZ) DESC,
 GREATEST(TRY_CAST(asof_ts AS TIMESTAMPTZ),TRY_CAST(received_at AS TIMESTAMPTZ)) DESC,snapshot_id DESC) AS rank
 FROM candles JOIN readings ON TRY_CAST(asof_ts AS TIMESTAMPTZ)<=candles.candle_at
 AND TRY_CAST(received_at AS TIMESTAMPTZ)<=candles.candle_at
) SELECT COUNT(DISTINCT candle_at) FROM chosen WHERE rank=1
AND candle_at-TRY_CAST(asof_ts AS TIMESTAMPTZ)<=INTERVAL '900 seconds'
AND EXISTS(SELECT 1 FROM json_each(walls_json) w WHERE
 TRY_CAST(COALESCE(json_extract_string(w.value,'$.mid'),json_extract_string(w.value,'$.strike')) AS DOUBLE)>0)
""").fetchone()[0]
conn.close()
assert count==len(matched_candles)
default=build_history('SPY',bars,rows)
report={'passed':True,'synthetic':False,'evidence_sha256':hashlib.sha256(raw).hexdigest(),'copied_spy_rows':len(rows),'scopes_checked':len(scopes),'candles_checked':len(bars),'default_scope':default['query_key'],'default_matching_nodes':default['candles_with_recorded_nodes'],'default_coverage':default['node_coverage'],'any_scope_candles_with_nodes':count,'candles_without_eligible_nodes_in_any_scope':len(bars)-count,'independent_sql_matches':count,'invalid_clock_rows':len(rows)-len(known),'scopes':results,'limitations':'Bounded store-copy diagnosis, not whole-source recovery, default-scope substitution, capture activation or deployed backend certification.'}
(HERE/'history-diagnosis.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='scopes'},indent=2))

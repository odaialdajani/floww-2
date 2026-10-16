"""Bounded integration gate. Does not restart services, trade, or invoke a model."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import time
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PLAN = ROOT / '.planning/unknowns/integration-reset-20261014.md'
SOURCE = [
    'backend/routes/price_history.py',
    'backend/server.py',
    'backend/services/price_node_history.py',
    'backend/services/solstice_scope.py',
    'backend/tests/services/test_price_history_admission.py',
    'backend/tests/services/test_price_history_diagnostics.py',
    'frontend/src/components/heatseeker/PriceNodeHistory.jsx',
    'frontend/src/components/heatseeker/PriceNodeHistory.scopeReview.test.jsx',
    'frontend/src/components/heatseeker/chart/scopeEcho.js',
    'frontend/src/components/heatseeker/RecordedPriceChart.jsx',
    'frontend/src/components/heatseeker/recordedPriceChartData.js',
    'frontend/src/components/heatseeker/RecordedPriceChart.integrity.test.jsx',
    'frontend/src/components/TrinityView.jsx',
    'frontend/src/components/TrinityView.test.jsx',
    'frontend/src/components/triad/TriadDesk.jsx',
    'frontend/src/components/heatseeker/SkylitDashboard.jsx',
    'frontend/src/components/heatseeker/SkylitDashboard.test.jsx',
    'frontend/src/components/heatseeker/SkylitHeatmapGrid.jsx',
    'frontend/src/components/heatseeker/ExactContractReview.admission.test.jsx',
    'frontend/src/components/heatseeker/RangeAnalyticsWorkspace.jsx',
    'frontend/src/components/heatseeker/RangeAnalyticsWorkspace.test.jsx',
    'frontend/src/components/flowseeker/CostCaption.test.jsx',
    *[f'frontend/src/components/heatseeker/{name}.{ext}' for name in ['ReviewInspector','HeatmapLandmarks'] for ext in ['jsx','css','test.jsx']],
]
EXPECTED_OUTPUTS = {'inventory.json','api.json','browser.cjs','browser.json','solstice.png','triad.png','verify.py','gate.json','continuation-browser.cjs','continuation-browser.json','synthetic-chart.png','history-diagnosis.py','history-evidence.json','history-diagnosis.json','history-review.cjs','history-review.json','history-saved-view.png'}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def git(*args):
    return subprocess.check_output(['git','-C',str(ROOT),*args])

def get(url):
    with urllib.request.urlopen(url,timeout=30) as response:
        assert response.status == 200, url
        return response.read()

parser = argparse.ArgumentParser()
parser.add_argument('--tests',action='store_true',help='Also rerun the full frontend, targeted backend and make checks')
args = parser.parse_args()
started = time.monotonic()
report = {'passed':False, 'checks':[], 'tests':[], 'limitations':'This gate verifies the bounded delivered changes, not whole-product acceptance or commissioning.'}
try:
    inventory = json.loads((HERE/'inventory.json').read_text())
    assert ROOT.name == 'floww-unified' and (ROOT/'frontend/package.json').is_file()
    assert PLAN.is_file() and PLAN.stat().st_size > 1000
    for name in SOURCE:
        assert (ROOT/name).is_file(), name
    for name in EXPECTED_OUTPUTS - {'gate.json'}:
        assert (HERE/name).is_file(), name
    assert {p.name for p in HERE.iterdir()} <= EXPECTED_OUTPUTS, 'Unexpected output/temp file'
    report['checks'].append('Exact plan/source/evidence paths exist; output directory contains only required artifacts')

    baseline = inventory['head']
    assert subprocess.run(['git','-C',str(ROOT),'merge-base','--is-ancestor',baseline,'HEAD']).returncode == 0, 'Baseline is no longer an ancestor; rebaseline required'
    assert git('branch','--show-current').decode().strip() in {inventory['branch'],'fix/floww-integration-reset-20261015'}
    assert sha(Path(inventory['preview']['path'])) == inventory['preview']['sha256']
    original = Path(inventory['original_ledger']['path'])
    assert sha(original) == inventory['original_ledger']['sha256']
    original_tasks = json.loads(original.read_text())['tasks']
    retained = [{k:v for k,v in row.items() if k != 'current_review'} for row in inventory['obligations']]
    assert retained == original_tasks and len(retained) == 62
    assert len({t['id'] for t in retained}) == len(retained)
    assert len(inventory['branches']) == inventory['branch_count'] == 82
    assert len(inventory['worktrees']) == inventory['worktree_count'] == 41
    report['checks'].append('All 62 original obligations/fields and original preview retained; all 82 branches and 41 worktrees inventoried')

    authorized_test = 'frontend/src/components/flowseeker/CostCaption.test.jsx'
    protected = {path:digest for path,digest in inventory['protected_hashes'].items() if path != authorized_test}
    for path,digest in protected.items():
        assert sha(ROOT/path) == digest, f'Protected file changed: {path}'
    subprocess.run(['git','-C',str(ROOT),'diff','--quiet','HEAD','--',*protected],check=True)
    allowed = set(SOURCE) | {'.planning/STATE.md','.planning/ROADMAP.md',str(PLAN.relative_to(ROOT)),'kanban/BOTTLENECK_ALERTS.md'}
    allowed |= {str((HERE/name).relative_to(ROOT)) for name in EXPECTED_OUTPUTS}
    status = git('status','--porcelain=v1','-z','--untracked-files=all')
    changed = [row[3:].decode() for row in status.split(b'\0') if row]
    assert set(changed) <= allowed, f'Unrelated changed files: {set(changed)-allowed}'
    subprocess.run(['git','-C',str(ROOT),'diff','--check'],check=True)
    report['changed_paths'] = changed
    report['source_sha256'] = {p:sha(ROOT/p) for p in SOURCE}
    report['checks'].append(f"{len(protected)} protected files match baseline and HEAD; the one authorized Screener test is scoped; only reviewed source/docs/evidence plus pre-existing kanban note are dirty")

    db = sqlite3.connect('file:/Users/nav/.hermes/state.db?mode=ro',uri=True)
    try:
        loops = [(key,json.loads(value)) for key,value in db.execute("select key,value from state_meta where key like 'loop:%'")]
    finally:
        db.close()
    matches = [(key,value['status']) for key,value in loops if value.get('prompt') == 'continue wokring keep testing bots making sure no dead ends or isses or gaps']
    assert matches and all(status == 'cleared' for _,status in matches), matches
    report['loop_states'] = matches
    report['checks'].append('Every persisted copy of the requested verification loop is cleared')

    html = get('http://127.0.0.1:3000/').decode()
    script = re.search(r'src="([^"]*main\.[a-f0-9]+\.js)"',html)
    assert script, 'Rebuilding placeholder/missing bundle'
    asset = script.group(1)
    disk = ROOT/'frontend/build'/asset.lstrip('/')
    assert disk.is_file() and get('http://127.0.0.1:3000'+asset) == disk.read_bytes()
    assert all((ROOT/p).stat().st_mtime <= disk.stat().st_mtime for p in SOURCE if p.startswith('frontend/') and not p.endswith('test.jsx'))
    css = re.search(r'href="([^"]*main\.[a-f0-9]+\.css)"',html)
    assert css and get('http://127.0.0.1:3000'+css.group(1)) == (ROOT/'frontend/build'/css.group(1).lstrip('/')).read_bytes()
    report['bundle'] = disk.name
    get('http://127.0.0.1:8002/health')
    live_history = json.loads(get('http://127.0.0.1:8002/api/heatseeker/price-history/SPY?days=1&interval_minutes=30'))
    assert 'price_failure' in live_history and 'node_coverage' in live_history, 'Review worker has not loaded history diagnostics'
    recorder = json.loads(get('http://127.0.0.1:8002/api/solstice/recorder_health'))
    assert recorder['background_capture']['enabled'] is False
    assert recorder['capture']['worker_state'] == 'absent'
    report['runtime_probe'] = {'history_price_status':live_history.get('price_status'),
                               'history_failure':live_history.get('price_failure'),
                               'capture_enabled':False,'capture_worker':'absent'}
    browser = json.loads((HERE/'browser.json').read_text())
    assert browser['bundle'] == disk.name
    assert browser['passed'] and not browser['errors'] and not browser['blocked']
    assert not browser.get('transportErrors')
    assert not browser.get('networkErrors'), browser.get('networkErrors')
    solstice = next(r for r in browser['checks'] if r['desk']=='Solstice' and 'candleCount' in r)
    assert int(solstice['candleCount']) > 0
    assert solstice['geometry']['gridRight'] <= solstice['geometry']['inspectorLeft']+1
    assert any(row['desk']=='Triad' and row.get('tabs')==4 for row in browser['checks'])
    report['checks'].append('Served bundle equals fresh disk build; live review API has history diagnostics with capture off; actual browser verifies candles, landmarks, shared tabs and nonoverlapping inspector')

    continuation = json.loads((HERE/'continuation-browser.json').read_text())
    assert continuation['passed'] and continuation['bundle'] == disk.name
    assert not continuation['pageErrors'] and not continuation['blockedMutations']
    assert {row['route'] for row in continuation['routeSmoke']} == {'flowseeker-pro','heatseeker','trinity','skylit','steal-three','portfolio','journal','public'}
    assert len(continuation['routeSmoke']) == 8
    assert all(continuation['syntheticChart'][key] for key in ['synthetic','passed','unknownVolumeKeptGap','sparsePremiumKeptGap','replayExcludedFuturePremium'])
    report['checks'].append('All eight workspace shells checked; isolated synthetic compiled-chart test preserves volume/premium gaps and excludes future replay prices')

    history = json.loads((HERE/'history-review.json').read_text())
    assert history['passed'] and history['bundle'] == disk.name and not history['synthetic']
    assert history['backendReloadAuthorized'] and history['backendDiagnosticsLoaded']
    assert history['noScopeSubstitution'] and history['candlesWithRecordedNodes'] > 0 and history['drawnSavedLines'] > 0
    audit = json.loads((HERE/'history-diagnosis.json').read_text())
    assert audit['passed'] and audit['evidence_sha256'] == sha(HERE/'history-evidence.json')
    assert audit['any_scope_candles_with_nodes'] == audit['independent_sql_matches']
    assert audit['any_scope_candles_with_nodes'] + audit['candles_without_eligible_nodes_in_any_scope'] == audit['candles_checked']
    report['backend_runtime'] = {'new_diagnostics_loaded':history['backendDiagnosticsLoaded'],'reload_authorized':history['backendReloadAuthorized'],'limitation':'Review backend on port 8002 only; trading and capture remain disabled.'}
    report['checks'].append('Actual older saved view renders observed nodes with exact scope; independent stored-data SQL and Python checks agree; backend runtime status explicitly disclosed')

    if args.tests:
        python = Path('/Users/nav/Documents/GitHub/floww-2/backend/.venv/bin/python')
        assert python.is_file()
        commands = [
            (ROOT/'frontend',['npm','test','--','--watchAll=false','--runInBand','--detectOpenHandles']),
            (ROOT/'backend',[str(python),'-m','pytest','tests/services/test_price_history_admission.py','tests/services/test_price_history_diagnostics.py','tests/services/test_price_history_scope.py','tests/services/test_price_history_recording.py','tests/services/test_price_history_volume.py','tests/services/test_price_node_chart_intervals.py','tests/services/test_price_node_value_guards.py','tests/services/test_recorded_price_levels.py','tests/services/test_scope_echo.py','tests/solstice/test_r14_window_producer.py','tests/routes/test_daily_checklist_truth.py','tests/services/test_triad_projection_backend.py','tests/services/test_price_history_contract.py','tests/services/test_price_history_horizons.py','tests/services/test_price_history_sessions.py','-q','-p','no:cacheprovider']),
            (ROOT,['make','test']),
        ]
        import os
        for cwd,command in commands:
            now = time.monotonic()
            result = subprocess.run(command,cwd=cwd,env={**os.environ,'CI':'true'},capture_output=True,text=True,timeout=300)
            output = result.stdout+result.stderr
            summary = [line for line in output.splitlines() if re.search(r'^(Test Suites:|Tests:|Time:|\d+ passed|PASS:)',line)]
            row = {'cwd':str(cwd),'command':command,'exit_code':result.returncode,'elapsed_s':round(time.monotonic()-now,3),'summary':summary,'output_sha256':hashlib.sha256(output.encode()).hexdigest(),'warnings':{'react_act':'not wrapped in act' in output,'late_exit':'Jest did not exit' in output,'open_handle':'Jest has detected the following' in output}}
            report['tests'].append(row)
            print(json.dumps(row))
            assert result.returncode == 0, output[-4000:]
        report['checks'].append('Clean rerun: full frontend, targeted backend and make test passed without skips added')
    report['passed'] = True
finally:
    report['elapsed_s'] = round(time.monotonic()-started,3)
    (HERE/'gate.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

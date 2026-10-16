"""Recheck the bounded engineering receipt; never grants owner acceptance.

Run --live to read back the exact published head, hosted jobs, preview backing,
provider controls and served bundle. No writes, activation, merges or retries.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_fingerprint():
    paths = [p for p in git('ls-files', 'backend').splitlines()
             if p.endswith('.py') and '/tests/' not in p]
    value = hashlib.sha256()
    for p in sorted(paths):
        value.update((p+'\0'+sha(ROOT/p)+'\n').encode())
    return value.hexdigest()


def get(path):
    with urllib.request.urlopen('http://127.0.0.1:8002'+path, timeout=35) as response:
        assert response.status == 200
        return json.load(response)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true')
    args = parser.parse_args()
    assert (HERE/'manifest.json').is_file(), 'Required completion manifest missing'
    manifest = json.loads((HERE/'manifest.json').read_text())
    assert {p.name for p in HERE.iterdir() if p.is_file()} == set(manifest['artifacts']) | {'manifest.json'}
    for name, digest in manifest['artifacts'].items():
        assert sha(HERE/name) == digest, name+' changed'
    assert source_fingerprint() == manifest['backend_source_fingerprint'], 'Untested backend source drift'
    for path, digest in manifest['protected_hashes'].items():
        assert sha(ROOT/path) == digest, 'Protected path drift: '+path
    for path in manifest['concurrent_unrelated']:
        assert (ROOT/path).is_file(), 'Concurrent work disappeared'
    changed = set(git('diff', '--name-only', manifest['baseline_head'], 'HEAD').splitlines())
    owned = set(manifest['owned_paths'])
    assert all(p in owned or p.startswith(tuple(manifest['owned_dirs'])) for p in changed), \
        'Paths outside our ownership changed: ' + str(sorted(changed - owned))
    assert not changed.intersection(manifest['concurrent_unrelated']), 'Concurrent work was committed'
    reviews = [json.loads((HERE/f'branch-review-{n}.json').read_text()) for n in [0, 1]]
    rows = [row for review in reviews for row in review['rows']]
    assert len(rows) == len({r['sha'] for r in rows}) == 133
    assert {r['sha'] for r in rows} == set(manifest['reviewed_shas'])
    assert all(r['evidence'] for r in rows)
    ledger = json.loads((HERE/'original-obligations.json').read_text())
    original = json.loads(Path(manifest['original_ledger']['path']).read_text())
    assert sha(Path(manifest['original_ledger']['path'])) == manifest['original_ledger']['sha256']
    original_rows = original['tasks'] if 'tasks' in original else original['obligations']
    assert ledger == original_rows and len(ledger) == 62
    assert sum(row['status']=='EXTERNAL_HOLD' for row in ledger) == 7
    checks = json.loads((HERE/'checks.json').read_text())
    for key in ['backend_final', 'backend_prior_coverage', 'frontend_full', 'focused_recovery', 'ruff', 'bandit', 'truth', 'make_test']:
        assert checks[key]['exit_code'] == 0, key+' not passed'
    assert checks['backend_prior_coverage']['coverage_percent'] >= 60
    browser = json.loads((HERE/'browser.json').read_text())
    assert browser['passed'] and not browser['synthetic']
    assert browser['triadReviewedScope'] == 'next'
    assert len(browser['checks']) == 8 and int(browser['priceCandles']) > 0
    assert not browser['pageErrors'] and not browser['httpErrors'] and not browser['blockedWrites']
    latency = json.loads((HERE/'latency.json').read_text())
    assert latency['passed'] and len(latency['runs']) == 3
    assert all(r['candles'] > 0 and not r['httpErrors'] for r in latency['runs'])
    head = git('rev-parse', 'HEAD')
    live = None
    if args.live:
        branch = git('branch', '--show-current')
        assert branch == manifest['branch']
        assert git('ls-remote', 'origin', 'refs/heads/'+branch).split()[0] == head
        runs = json.loads(subprocess.check_output([
            'gh','run','list','--branch',branch,'--commit',head,'--limit','20',
            '--json','databaseId,name,status,conclusion,headSha'], cwd=ROOT, text=True))
        selected = [r for r in runs if r['name']=='CI/CD']
        assert selected, 'No hosted CI run at exact head'
        ci = selected[0]
        assert ci['headSha']==head and ci['status']=='completed' and ci['conclusion']=='success', ci
        jobs = json.loads(subprocess.check_output(['gh','run','view',str(ci['databaseId']),
                          '--json','headSha,jobs'], cwd=ROOT, text=True))
        assert jobs['headSha']==head
        by_name = {j['name']:j for j in jobs['jobs']}
        for name in ['backend-tests','frontend-build','docker-build']:
            assert by_name[name]['conclusion']=='success', name+' not passed'
        runtime = json.loads((HERE/'runtime.json').read_text())
        assert runtime['backend_source_fingerprint']==manifest['backend_source_fingerprint']
        listeners = subprocess.check_output(['lsof','-t','-nP','-iTCP:8002','-sTCP:LISTEN'], text=True).split()
        assert listeners == [str(runtime['pid'])], 'Preview process changed since runtime verification'
        health = get('/api/health')
        assert health['checks']['public_api']['key_configured']
        assert health['institutional']['budget']['max_inflight']==4
        recorder = get('/api/solstice/recorder_health')
        assert recorder['durable'] and recorder['backing']=='file'
        assert not recorder['capture']['worker_enabled'] and not recorder['background_capture']['enabled']
        control = get('/api/heatseeker/price-history/SPY?days=1&interval_minutes=30')
        assert control['price_status']=='available' and control['frames']
        with urllib.request.urlopen('http://127.0.0.1:3000/', timeout=15) as response:
            index = response.read().decode()
        assert browser['bundle'] in index
        asset = re.search(r'src="([^"]*'+re.escape(browser['bundle'])+r')"', index).group(1)
        with urllib.request.urlopen('http://127.0.0.1:3000/'+asset.lstrip('/'), timeout=20) as response:
            served = hashlib.sha256(response.read()).hexdigest()
        assert served == sha(ROOT/'frontend/build/static/js'/browser['bundle'])
        live = {'head':head,'ci_run':ci['databaseId'],'jobs':{n:by_name[n]['conclusion'] for n in ['backend-tests','frontend-build','docker-build']},'control_candles':len(control['frames']),'last_candle_at':control.get('last_candle_at'),'capture_off':True}
    print(json.dumps({'passed':True,'live_checked':args.live,'reviewed_commit_rows':133,
                     'original_obligations_preserved':62,'owner_holds_preserved':7,
                     'commissioning':'HOLD','live':live}, indent=2))


if __name__=='__main__':
    main()

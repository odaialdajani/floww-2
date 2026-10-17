#!/usr/bin/env python3
"""Read-only research-packet gate; writes only VERIFICATION_REPORT.json.

This validates the packet and preservation, not whether proposed chart features
are implemented. Re-run with the same canonical checkout before handoff.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

PACK = Path(__file__).resolve().parent
ROOT = PACK.parents[2]
EXPECTED = {
    'MASTER_PLAN.md', 'SPARK_HANDOFF.md', 'CONTRACT.md', 'SOURCES.md',
    'VIDEO_TRANSCRIPT.md', 'RESEARCH_REPORTS.md', 'CAPABILITIES.json',
    'IMPLEMENTATION_TASKS.json', 'EVIDENCE.json', 'PRESERVATION_BASELINE.json',
    'MANIFEST.json', 'VERIFY.py', 'VERIFICATION_REPORT.json',
}
checks = []

def check(name, condition, details=None):
    checks.append({'check': name, 'passed': bool(condition), 'details': details})

def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def load(name):
    return json.loads((PACK/name).read_text())

def run():
    actual = {p.name for p in PACK.iterdir()}
    check('exact_artifact_set', actual <= EXPECTED and EXPECTED - actual <= {'VERIFICATION_REPORT.json'}, {'missing':sorted(EXPECTED-actual-{'VERIFICATION_REPORT.json'}),'unexpected':sorted(actual-EXPECTED)})
    for name in sorted(EXPECTED-{'VERIFICATION_REPORT.json'}):
        check('exists_nonempty:'+name, (PACK/name).is_file() and (PACK/name).stat().st_size > 0)
    if not all(c['passed'] for c in checks):
        return
    caps_doc, tasks_doc = load('CAPABILITIES.json'), load('IMPLEMENTATION_TASKS.json')
    caps, tasks = caps_doc['capabilities'], tasks_doc['blocks']
    capids = {c['id'] for c in caps}
    taskids = {t['id'] for t in tasks}
    check('capability_count_and_uniqueness',len(caps)==caps_doc['count']==143 and len(capids)==len(caps))
    check('blocks_and_microsteps',len(tasks)==tasks_doc['block_count']==29 and sum(len(t['steps']) for t in tasks)==tasks_doc['microstep_count']==145)
    categories = {'chart-basics','usability','panes','layouts','exposure','derived','projection','indicators','flow','darkpool','delta','sidecars','alerts','drawings','replay','plugins','positions','ai','hardening','rollout'}
    check('required_categories',categories <= {c['category'] for c in caps},sorted(categories-{c['category'] for c in caps}))
    check('all_capabilities_disposed',all(c['current_status'] in {'partial','new','data-gated','out-of-scope'} and c['target_phase'] in {f'P{i}' for i in range(9)} and c['implementation_block'] in taskids and all(c[k] for k in ['feature','prerequisite','acceptance','sources']) for c in caps))
    assignments = [c for t in tasks for c in t['capability_ids']]
    check('one_task_assignment_per_capability',set(assignments)==capids and len(assignments)==len(capids) and all(c['id'] in next(t['capability_ids'] for t in tasks if t['id']==c['implementation_block']) for c in caps))
    check('full_red_green_tasks',all(all(t[k] for k in ['proposed_implementation_files','proposed_test_file','acceptance','test_command']) and len(t['steps'])==5 and t['command_status'].startswith('future acceptance') for t in tasks))
    check('dependency_ids_exist',all(set(t['depends_on'])<=taskids and t['id'] not in t['depends_on'] for t in tasks))
    seen=set()
    while True:
        nxt={t['id'] for t in tasks if set(t['depends_on']) <= seen}
        if nxt<=seen: break
        seen |= nxt
    check('dependency_dag',seen==taskids,sorted(taskids-seen))
    master=(PACK/'MASTER_PLAN.md').read_text()
    mandatory=['S²','VOMMA','VANNA','Scroll as replay','900','TrinityView','AskLodestar','Lightweight Charts','Apache-2.0','Replay','Flow Bucket','TPO','Volume Profile','Nexus','SPARK_HANDOFF.md','capability','frozen','16.7ms']
    check('master_required_architecture',all(k in master for k in mandatory),[k for k in mandatory if k not in master])
    check('all_delivery_phases_present',all(f'**P{i} —' in master for i in range(9)))
    e=load('EVIDENCE.json')
    check('observed_backend_tests', len(e['test_runs'])==2 and all(t['exit_code']==0 for t in e['test_runs']) and 'Ran 8 tests' in e['test_runs'][0]['output'] and '53 passed' in e['test_runs'][1]['output'])
    check('frontend_blocker_not_fabricated',e['frontend_baseline']['exit_code']==127 and e['frontend_baseline']['status']=='blocked_missing_local_craco')
    nim=e['nim_connectivity']
    check('nim_model_verified',nim['http_status']==200 and nim['returned_model']=='z-ai/glm-5.3' and nim['reply']=='NIM_GLM_53_OK')
    reviews=e['research_reviews']
    check('research_evidence_distinguishes_failures',len(e['initial_fanout'])==4 and sum(r['status']=='timed_out' for r in e['initial_fanout'])==3 and sum(r['status']=='completed' for r in e['initial_fanout'])==1 and all(r['persisted_model_identity']['providerID']=='nvidia' and r['persisted_model_identity']['modelID']=='z-ai/glm-5.3' for r in e['initial_fanout']) and len(reviews)==4 and all(r['status']=='incomplete' for r in reviews) and {r['lane'] for r in reviews}=={'chart-engine','workspace-ux','test-gates','refuter'})
    check('parent_fallback_audits_grounded',len(e['parent_inline_audits'])==3 and all(a['status']=='completed' and a['evidence'] for a in e['parent_inline_audits']))
    check('independent_refutation_disposed',e['independent_review']['status']=='reviewed_and_applied' and e['independent_review'].get('dispositions') and all(d['status'] in {'applied','explicit_hold','rejected_with_evidence'} for d in e['independent_review']['dispositions']))
    contract=(PACK/'CONTRACT.md').read_text()
    dispositions=e['independent_review']['dispositions']
    check('all_eight_review_findings_retained',len(dispositions)==8 and {d['id'] for d in dispositions}=={f'IR{i:02d}' for i in range(1,9)})
    required_contract=['characterized_end_time <= R','recorded_revision_available_at <= R','inferred_bar_end','newer malformed/incomplete observation supersedes','observed-subset','cross-owner','private GET/list/export','replay-origin live-alert','hidden during time-faithful practice','context generation']
    check('review_temporal_coverage_identity_safety_contracts',all(k in contract for k in required_contract),[k for k in required_contract if k not in contract])
    check('adapter_inverse_context_export_contracts',all(k in master for k in ['xToTime','yToPrice','seriesId','subscribeViewport','idempotent unsubscribe','captureEngineImage','Workspace-level `exportComposite`']))
    task_by_id={t['id']:t for t in tasks}
    def closure(ids):
        found=set(ids)
        while True:
            expanded=found | {dep for tid in found for dep in task_by_id[tid]['depends_on']}
            if expanded==found: return found
            found=expanded
    core_closure=closure(['B28','B29'])
    check('supported_release_not_blocked_by_gated_branches',not {'B13','B19','B20','B21','B22','B26'} & core_closure and 'B13' not in task_by_id['B17']['depends_on'] and 'B19' not in task_by_id['B23']['depends_on'],sorted(core_closure))
    profiles=tasks_doc['release_profiles']
    check('release_profiles_and_variant_gates', {r['id'] for r in profiles}=={'R1','R2','R3'} and all(set(r['candidate_capability_ids'])<=capids and set(r['foundation_blocks'])<=taskids for r in profiles) and all(t['prerequisite_disposition_contract']['rule'] for t in tasks) and all(set(v['depends_on'])<=taskids for t in tasks for v in t.get('variants',[])))

    r2=e.get('round2',{})
    check('round2_failure_and_corruption_disposed',r2.get('status')=='reviewed_and_applied' and len(r2.get('lanes',[]))==4 and sum(r['accepted_status']=='failed' for r in r2['lanes'])==2 and sum(r['accepted_status']=='rejected_unusable' for r in r2['lanes'])==1 and sum(r['accepted_status']=='usable_report_source_verified' for r in r2['lanes'])==1 and not any(r['findings_accepted'] for r in r2['lanes'] if r['accepted_status'] in {'failed','rejected_unusable'}))
    check('round2_primary_pages_retrieved',len(r2.get('primary_sources',[]))==10 and all(r['status']=='retrieved' and r['returned_characters']>1000 and len(r['content_sha256'])==64 for r in r2['primary_sources']))
    baseline_ids={f'C{i:03d}' for i in range(1,112)}
    added_ids={f'C{i:03d}' for i in range(112,144)}
    invariant_rows=[r for t in tasks for r in t.get('round2_acceptance_invariants',[])]
    check('round2_retains_original_ids_and_assigns_all_additions',capids==baseline_ids|added_ids and set(r2['retained_original_capability_ids'])==baseline_ids and set(r2['added_capability_ids'])==added_ids and len(invariant_rows)==32 and {r['capability_id'] for r in invariant_rows}==added_ids)
    sources=(PACK/'SOURCES.md').read_text()
    check('round2_source_ids_and_per_block_invariants',all(all(s in sources for s in c['sources']) for c in caps if c['id'] in added_ids) and all(r['criterion'] and r['fixture_requirement'] for r in invariant_rows))
    terms=['minimum8 measured minutes','68%','fifth eligible period','starred > active > built-in','takeScreenshot','not a custom intraday/weekly resampler','future acceptance']
    combined=master+'\n'+json.dumps(tasks_doc)
    check('round2_detail_coverage',all(k in combined for k in terms),[k for k in terms if k not in combined])
    check('round2_parent_characterization_and_honest_refutation',r2['parent_characterization']['exit_code']==0 and r2['parent_characterization']['observations']['missing_volume_becomes_zero'] and r2['parent_characterization']['observations']['positive_infinite_volume_accepted'] and r2['independent_round2_refutation']['status']=='unavailable' and len(r2['parent_adversarial_dispositions'])==6 and all(r['status'] in {'applied','explicit_hold','rejected_with_evidence'} for r in r2['parent_adversarial_dispositions']))

    check('live_probe_actual',e['live_chart_probe']['http_status']==200 and e['live_chart_probe']['candles']==376 and e['live_chart_probe']['candles_with_recorded_nodes']==12)
    check('video_provenance',e['video']['status']=='retrieved_english_transcript' and e['video']['video_id']=='9Hn_OLBJRVY' and len((PACK/'VIDEO_TRANSCRIPT.md').read_text())>10000)
    b=load('PRESERVATION_BASELINE.json')
    check('canonical_root',str(ROOT)==b['root'])
    check('unchanged_head_branch',git('rev-parse','HEAD').decode().strip()==b['head'] and git('branch','--show-current').decode().strip()==b['branch'])
    changed=[]
    for rel,oldhash in b['tracked_hashes'].items():
        p=ROOT/rel
        if not p.is_file() or digest(p)!=oldhash: changed.append(rel)
    check('all_baseline_tracked_bytes_preserved',not changed,changed)
    current_paths=set(p.decode() for p in git('ls-files','-z').split(b'\0') if p)
    check('tracked_path_set_preserved',current_paths==set(b['tracked_hashes']),sorted(current_paths.symmetric_difference(b['tracked_hashes'])))
    initial=bytes.fromhex(b['status_hex']).split(b'\0')
    now=git('status','--porcelain=v1','-z','--untracked-files=all').split(b'\0')
    prefix=str(PACK.relative_to(ROOT))+'/'
    filtered=[row for row in now if row and not row[3:].decode().startswith(prefix)]
    check('preexisting_git_status_preserved',filtered==[row for row in initial if row],{'baseline_entries':len([r for r in initial if r]),'current_other_entries':len(filtered)})
    own=[r[3:].decode() for r in now if r and r[3:].decode().startswith(prefix)]
    check('only_expected_outputs_added',{p[len(prefix):] for p in own} <= EXPECTED,own)
    manifest=load('MANIFEST.json')
    covered=EXPECTED-{'MANIFEST.json','VERIFICATION_REPORT.json'}
    check('manifest_coverage',set(manifest['artifact_sha256'])==covered)
    check('artifact_integrity',all(digest(PACK/name)==sha for name,sha in manifest['artifact_sha256'].items()))
    # Validate literal existing file:line citations; proposed paths are elsewhere.
    citations=re.findall(r'`((?:frontend|backend|tests)/[^`\s:]+):([0-9]+)',master)
    missing=[f'{path}:{line}' for path,line in citations if not (ROOT/path).is_file() or len((ROOT/path).read_text().splitlines())<int(line)]
    check('source_citations_exist',bool(citations) and not missing,missing)
    check('no_credential_values_in_packet',not any(re.search(r'(?<![A-Za-z0-9_-])(?:nvapi-[A-Za-z0-9_-]{20,}|sk-(?:or-v1-)?[A-Za-z0-9_-]{24,}|Bearer\s+[A-Za-z0-9._-]{20,}|NVIDIA_API_KEY\s*=\s*[\"\']?[A-Za-z0-9_-]{15,})',p.read_text()) for p in PACK.iterdir() if p.is_file() and p.suffix in {'.md','.json'}))

try:
    run()
except Exception as exc:
    check('gate_exception',False,type(exc).__name__+': '+str(exc))
report={'status':'PASS' if checks and all(c['passed'] for c in checks) else 'FAIL','gate_scope':'research artifacts and preservation only; not feature readiness','checks':checks,'artifact_count':len(EXPECTED),'required_capabilities':143,'required_blocks':29}
(PACK/'VERIFICATION_REPORT.json').write_text(json.dumps(report,indent=2)+'\n')
for c in checks:
    print(('PASS' if c['passed'] else 'FAIL')+' '+c['check']+((' '+json.dumps(c['details'])) if not c['passed'] else ''))
print(report['status']+' RESEARCH_PACKET_GATE')
sys.exit(0 if report['status']=='PASS' else 1)

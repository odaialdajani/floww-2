# PR #44–#87 current-main audit

Candidate: `6716946b109e43ced81bec6f2fec9c0c46332f14`. Exactly 44 numbered entries. Read-only engineering review; **not owner acceptance**.

## Result

{
  "entries": 44,
  "range": [
    44,
    87
  ],
  "classification_counts": {
    "current intent retained": 26,
    "owner-hold or unverified": 7,
    "superseded/declined": 9,
    "confirmed repair needed": 2
  },
  "fully_paginated_and_count_reconciled": 44,
  "merged_ancestor_count": 43,
  "not_merged": [
    85
  ],
  "distinct_reproduced_actionable_gaps": [
    "FLOW-FUSION-LOSS"
  ],
  "not_owner_acceptance": true,
  "exhaustive_semantic_acceptance": false,
  "explicit_large_scope_residuals": [
    48,
    51,
    56,
    57,
    84
  ],
  "completion_claim": "44/44 entries accounted for at explicitly stated review depth; all requested API surfaces paginated. Not exhaustive behavioral acceptance of every carried stack, nor whole-product/owner commissioning."
}

**One distinct reproducible gap:** FLOW-FUSION-LOSS, attributed to #55/#73. Exact current producer and route fusion statement turn a measured flow score of 35.0 into 0.0 and discard its evidence key before persistence. Offline failing-test proposal is attached to both rows.

## Depth and exclusions

- All 44 file/commit/discussion/review-comment/review endpoints were fully paginated and fetched counts reconciled to fresh PR detail counts (reviews have terminal page proof; no reviews existed). All acceptance-relevant discussion was read (#85 two comments); all other endpoints were empty.
- Every row includes historical commit identities, a changed-file inventory and candidate-pinned definitions/callers/test references. Semantic reading focused on the paths named in each row. Large carried stacks (#48/#51/#56/#57/#84) are not exhaustively behavior-accepted; residual scope is explicitly stated.
- No pytest/Jest suite, compiled browser flow, provider probe, durable production-store operation, service action, capture/trading or paid request was run. Read-only syntax/ignore probes, candidate pure functions and exact route-stage synthetic reproduction are the only new execution evidence.
- Protected model artifact payloads, ignored credentials and runtime records were not scanned. Historical source-containing API patches were not retained in reports. Source reads are candidate-pinned; old document paths/counts and successful merges are never current feature proof.

## Execution evidence

```json
{
  "checks": {
    "truth_audit_syntax": {
      "exit_code": 0,
      "stderr": ""
    },
    "runtime_store_ignore_probe": {
      "exit_code": 0,
      "matched_synthetic_paths": [
        "backend/data/review-fixture.sqlite3",
        "backend/data/review-fixture.sqlite3-wal",
        "data/review-fixture.duckdb"
      ]
    },
    "pure_function_probes": [
      {
        "name": "R6 label_touch prefix stability",
        "result": "pass",
        "before": {
          "label": "target_hit",
          "censored": false,
          "version": "outcome.v1"
        },
        "after_future_corruption": {
          "label": "target_hit",
          "censored": false,
          "version": "outcome.v1"
        }
      },
      {
        "name": "momentum bool and malformed sentinel",
        "result": "pass",
        "inputs": [
          true,
          false,
          null,
          "garbage",
          85,
          10
        ],
        "outputs": [
          50,
          50,
          50,
          50,
          85,
          10
        ]
      },
      {
        "name": "post-2007 US DST rule boundary",
        "result": "pass",
        "utc_instants": [
          "2026-03-08T06:59:59+00:00",
          "2026-03-08T07:00:00+00:00",
          "2026-11-01T05:59:59+00:00",
          "2026-11-01T06:00:00+00:00"
        ],
        "offsets": [
          -5,
          -4,
          -4,
          -5
        ]
      }
    ]
  },
  "reproductions": {
    "flow_evidence_lost": {
      "method": "Exact candidate _universe_scan_conviction AST executed with in-memory fake alert feed and pure rank_one module, then exact candidate universe_scan fused-assignment AST executed. No server, broker, store or real feed imported.",
      "producer_conviction": 35.0,
      "producer_flow_status": "ok",
      "producer_flow_key": "fixture-flow",
      "consumer_flow_status": "missing",
      "consumer_flow_key": null,
      "preservation_assertion": false,
      "consumer_before_persistence_conviction": 0.0
    }
  }
}
```

## Repository preservation

Concurrent changes appeared after the clean baseline: modified backend/server.py; untracked backend/services/snapshot_writes.py and backend/tests/services/test_snapshot_write_admission.py. This agent did not create, edit, delete, stage or execute those files and did not read their working-tree contents. Source review is pinned with git show to the candidate SHA, so concurrent edits do not silently alter citations. Only review-1.json and review-1.md were written by this agent.

Final HEAD: `6716946b109e43ced81bec6f2fec9c0c46332f14`. Foreign status paths preserved, not modified.

## #44 — fix(r6-4): semantic explainer binding, mounted deterministic explainer

**Classification: current intent retained**

The suffix-number rejection, deterministic template rendering and interaction-state promotion guard survive in validate_explainer_output. explainWall is consumed by WallInspector, which remains in the dashboard SelectedWallBlock path; not inferred from a stranded library. Stacked #41–43 scope is inventoried, not independently reaccepted by this row.

PR: https://github.com/odaialdajani/floww-2/pull/44
Historical head: https://github.com/odaialdajani/floww-2/commit/08a34354fcc2ee14e1fc031a0939b3e60c9ccaf9
Merge: https://github.com/odaialdajani/floww-2/commit/6d4a7a7052d76135c46e9b315756036f3a514f61; ancestor of candidate: True.

API: files: 27 records / 1 pages, commits: 4 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [backend/services/solstice_evidence.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/solstice_evidence.py#L242) — `def validate_explainer_output|def render_clause|status promotion`; lines 242, 267, 367, 375
- [frontend/src/components/heatseeker/WallInspector.jsx](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/WallInspector.jsx#L2) — `explainWall|SelectedWallExplainer`; lines 2, 332
- [backend/tests/solstice/test_r6_4_red.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/solstice/test_r6_4_red.py#L25) — `def test_`; lines 25, 33, 64

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/f3224033887553abbbae05888bafd91a48b6043a
- https://github.com/odaialdajani/floww-2/commit/d75c41cbcb87579fe7847b50331a14ec4828398a
- https://github.com/odaialdajani/floww-2/commit/9147d1c59dbc5774e5e810accd870af9f45f9c44
- https://github.com/odaialdajani/floww-2/commit/08a34354fcc2ee14e1fc031a0939b3e60c9ccaf9

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #45 — fix(r6-5): prefix-stable outcomes, study mode, outcome job

**Classification: owner-hold or unverified**

Prefix-stable label_touch and complete-episode closure remain, with later multi-horizon/idempotency upgrades. Candidate pure-function probe preserved target_hit after later corrupt/conflicting observations. Original StudyMode component is now absent, not mounted: successor dashboard uses integrated study selection/review rather than the original standalone UI. Do not infer a repair requirement from this retired path. Comprehension commissioning/actual saved outcomes remain owner gates, not certified by this source review.

PR: https://github.com/odaialdajani/floww-2/pull/45
Historical head: https://github.com/odaialdajani/floww-2/commit/57cb02d49648edf0e0a5f46b56093cbaa26f2fd9
Merge: https://github.com/odaialdajani/floww-2/commit/2dbc5a58b284e7e31273f3abaf4f373532bb00ba; ancestor of candidate: True.

API: files: 36 records / 1 pages, commits: 7 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [backend/services/solstice_labels.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/solstice_labels.py#L20) — `def label_touch|def close_episodes|TOUCH_NO_BARRIER`; lines 20, 134, 140
- [backend/tests/solstice/test_r6_5_red.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/solstice/test_r6_5_red.py#L8) — `def test_`; lines 8, 20, 27, 46, 69, 95
- [frontend/src/components/heatseeker/SkylitDashboard.jsx](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/SkylitDashboard.jsx#L23) — `studyChoice|study focus|ReviewInspector`; lines 23, 35, 36, 484, 669, 671, 704, 708, 1140

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/f3224033887553abbbae05888bafd91a48b6043a
- https://github.com/odaialdajani/floww-2/commit/d75c41cbcb87579fe7847b50331a14ec4828398a
- https://github.com/odaialdajani/floww-2/commit/9147d1c59dbc5774e5e810accd870af9f45f9c44
- https://github.com/odaialdajani/floww-2/commit/08a34354fcc2ee14e1fc031a0939b3e60c9ccaf9
- https://github.com/odaialdajani/floww-2/commit/2c130f42cdc92be9003aa3c084bfea73404a98c5
- https://github.com/odaialdajani/floww-2/commit/6d6aacb896867a22d89a307b9cd7e60944de811e
- https://github.com/odaialdajani/floww-2/commit/57cb02d49648edf0e0a5f46b56093cbaa26f2fd9

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #46 — docs(r6): merge receipt for PRs #41-45; CLAUDE.md environment note

**Classification: current intent retained**

Machine-specific canonical-path note persists at CLAUDE.md:3–9; STATUS remains a historical receipt, not an assertion that R6 tests or a running deployment were verified at this candidate.

PR: https://github.com/odaialdajani/floww-2/pull/46
Historical head: https://github.com/odaialdajani/floww-2/commit/2f7821f67f3ba2312de5067b4adb00685d21f9b4
Merge: https://github.com/odaialdajani/floww-2/commit/e26aae2772d6f1b1bdd4f1a0f411164b5e12ac99; ancestor of candidate: True.

API: files: 2 records / 1 pages, commits: 1 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [CLAUDE.md](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/CLAUDE.md#L3) — `Environment note|machine-specific`; lines 3, 7
- [docs/solstice/STATUS.md](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/docs/solstice/STATUS.md#L384) — `R6|#41|#45`; lines 384, 390, 397, 400, 404, 407, 421, 433, 443

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/2f7821f67f3ba2312de5067b4adb00685d21f9b4

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #47 — fix(r6-holes): outcome job fail-closed + production route, wall linkage, keyboard test

**Classification: current intent retained**

close_episodes refuses incomplete episodes with NEED_EPISODE rather than default zero barriers. outcomes_close remains a registered research-write route; later attachment joins into decision reviews survive. Auth comes from global write-method middleware, not a local Depends annotation. The caller-supplied path design still explicitly defers scheduled price-path collection to commissioning.

PR: https://github.com/odaialdajani/floww-2/pull/47
Historical head: https://github.com/odaialdajani/floww-2/commit/2f69b7c342efedc52c1a978a7f74fc9d3dad23ee
Merge: https://github.com/odaialdajani/floww-2/commit/7fed60128b98da5335eb949e07b25ea71b6ca4e1; ancestor of candidate: True.

API: files: 8 records / 1 pages, commits: 1 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [backend/services/solstice_labels.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/solstice_labels.py#L140) — `NEED_EPISODE|def close_episodes`; lines 140, 167, 215, 227
- [backend/routes/solstice.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/routes/solstice.py#L5) — `outcomes/close|attach_outcomes`; lines 5, 342, 382, 383
- [backend/server.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/server.py#L3387) — `verify_api_key|include_router.solstice`; lines 3387, 3394, 3807, 3811, 3818
- [backend/tests/solstice/test_r6_5_red.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/solstice/test_r6_5_red.py#L69) — `episodeless|zone_without`; lines 69, 95

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/2f69b7c342efedc52c1a978a7f74fc9d3dad23ee

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #48 — feat(r8): review journal routes, frontend pill, outcome attach tests

**Classification: owner-hold or unverified**

Review journal routes, save-state validation, dashboard pill/save flow and outcome attachment survive. Current save passes ticker into save_decision_review and has an explicit missing-record check, strengthening the original route. PR contains 16 commits and 61 changed files (R7 stack, bars/Greek/time/Movers changes), so this is substantive journal/outcome-path verification, not blanket verification of all R7 behavior. Real recovery completeness and outcome availability are not established.

PR: https://github.com/odaialdajani/floww-2/pull/48
Historical head: https://github.com/odaialdajani/floww-2/commit/73ea67f68f4088cabcd9b6b56b3413546c745e60
Merge: https://github.com/odaialdajani/floww-2/commit/79b28ec25d4f9c3cedd983ecd14a27e88b2f8948; ancestor of candidate: True.

API: files: 61 records / 1 pages, commits: 16 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [backend/routes/solstice_review.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/routes/solstice_review.py#L41) — `decisions_list|save_review|save_decision_review`; lines 41, 91, 102, 116
- [backend/services/heatmap_history.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/heatmap_history.py#L305) — `def list_decisions|def save_decision_review|def attach_outcomes_to_decisions`; lines 305, 1098, 1161
- [frontend/src/components/heatseeker/SkylitDashboard.jsx](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/SkylitDashboard.jsx#L761) — `saveReview|skylit-review-pill`; lines 761, 1168, 1199
- [backend/tests/solstice/test_r8_04_review_journal.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/solstice/test_r8_04_review_journal.py#L100) — `def test_`; lines 100, 108, 149, 180, 219, 243, 274

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/d1e9cbbfc2493bc4f7715a27dd6706fbc1f2d02f
- https://github.com/odaialdajani/floww-2/commit/b071fcc1c41132b2f039e6310817c1d8da6b67a9
- https://github.com/odaialdajani/floww-2/commit/467e2318b623896572065f1f4e1b139206f2aa75
- https://github.com/odaialdajani/floww-2/commit/f8a84098c9284af9a6494e254036b4bd3bdfc2ce
- https://github.com/odaialdajani/floww-2/commit/e814b57a91b5b8e36ad605dd575593e71b0fac25
- https://github.com/odaialdajani/floww-2/commit/d4ca003809f89c976458f7750737ac00433c2ef0
- https://github.com/odaialdajani/floww-2/commit/70a3210d4a0bfea91b345ab8dc7b23c5e14ccc07
- https://github.com/odaialdajani/floww-2/commit/7de78639750d7f6b41233a30e2f1ba3f44272d11
- https://github.com/odaialdajani/floww-2/commit/16d3d714eb26daec9b55418d92528b7078b3b466
- https://github.com/odaialdajani/floww-2/commit/046a1357f1e2a77927d580f6f7f915758e41993b
- https://github.com/odaialdajani/floww-2/commit/21c523256e59d8da49109ecb4c456d26c388093e
- https://github.com/odaialdajani/floww-2/commit/36872db7834ad8013bdd56b7ba9b598415ec5c4f
- https://github.com/odaialdajani/floww-2/commit/69a8e30ea42061c4f078fa8685e153e7f8a0bc51
- https://github.com/odaialdajani/floww-2/commit/087c34378374e3339bb3ce51d81b3e3428816598
- https://github.com/odaialdajani/floww-2/commit/32b23cef99e9edbd5306a0d940b05e5660259151
- https://github.com/odaialdajani/floww-2/commit/73ea67f68f4088cabcd9b6b56b3413546c745e60

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #49 — fix(vex-sidebar): label structural anchors honestly in VEX/Charm views

**Classification: current intent retained**

The non-overlay VEX/Charm sidebar explicitly labels raw anchors GEX structural; active metric overlays remain separate. Current tests pin the VEX label rather than treating raw GEX totals as VEX data.

PR: https://github.com/odaialdajani/floww-2/pull/49
Historical head: https://github.com/odaialdajani/floww-2/commit/d9371e22ce0644a8c42316137d347a44701eda01
Merge: https://github.com/odaialdajani/floww-2/commit/2516e9c7187f7f959a5b38537b00faf8ca564dbb; ancestor of candidate: True.

API: files: 5 records / 1 pages, commits: 1 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [frontend/src/components/heatseeker/SkylitMetricsSidebar.jsx](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/SkylitMetricsSidebar.jsx#L99) — `summaryLabel|GEX structural`; lines 99, 101, 152
- [frontend/src/components/heatseeker/SkylitMetricsSidebar.test.jsx](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/SkylitMetricsSidebar.test.jsx#L38) — `structural anchors honestly`; lines 38

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/d9371e22ce0644a8c42316137d347a44701eda01

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #50 — style(r8-ui-blend): make R8 additions look like the heatmap

**Classification: current intent retained**

WallInspector uses shared table/note classes and missing delta/activity inputs remain unavailable rather than fabricated measured zeros. Later sidebar validation adds partial/unknown handling. Static CSS/JSX proof is not a current pixel/layout acceptance.

PR: https://github.com/odaialdajani/floww-2/pull/50
Historical head: https://github.com/odaialdajani/floww-2/commit/857e2067a50aa9a443f0165957481c3b3f200847
Merge: https://github.com/odaialdajani/floww-2/commit/c7f34885a470f9d516f664efef27f702ff8c4778; ancestor of candidate: True.

API: files: 10 records / 1 pages, commits: 2 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [frontend/src/components/heatseeker/WallInspector.jsx](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/WallInspector.jsx#L207) — `dUsable|vVal|skylit-compare-table|skylit-inspector-note`; lines 207, 213, 218, 223, 239, 242, 244, 249, 279, 316
- [frontend/src/App.css](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/App.css#L3680) — `skylit-compare-table|skylit-review-select`; lines 3680, 3693, 3698, 3705, 3714, 3715, 3720, 3726, 3730, 3738
- [frontend/src/components/heatseeker/SkylitMetricsSidebar.test.jsx](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/SkylitMetricsSidebar.test.jsx#L51) — `missing readings|genuine measured`; lines 51, 85

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/d9371e22ce0644a8c42316137d347a44701eda01
- https://github.com/odaialdajani/floww-2/commit/857e2067a50aa9a443f0165957481c3b3f200847

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #51 — fix(r8-audit-v2): close audit-V2 criticals + align dishonest math

**Classification: owner-hold or unverified**

Inspected authenticated brokerage reads, default-deny FLOWW_ENABLE_LIVE_PUBLIC submission gate, constrained LLM model identity, dev-token opt-in and 24h TTL. Those current controls remain; old CLAUDE unreachable PublicBroker wording is not used as safety proof. Vendor credential rotation/history purge were explicitly excluded and cannot be signed off here. This multi-surface security/math PR needs deeper independent route/units/security testing before whole-PR acceptance; no historical secret values were intentionally read or printed. Historical/current portfolio abs(quantity)*sign and volume GEX/VEX/Charm canonical scaler hunks were also inspected; those fixes remain, but no full security sweep or rotation proof is claimed.

PR: https://github.com/odaialdajani/floww-2/pull/51
Historical head: https://github.com/odaialdajani/floww-2/commit/6d44add0587ca5b6372099c2fcc24a573fb1354e
Merge: https://github.com/odaialdajani/floww-2/commit/dbbc66f441e7dcc93b8a903e93311ef8321f484a; ancestor of candidate: True.

API: files: 29 records / 1 pages, commits: 1 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [backend/routes/public_brokerage.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/routes/public_brokerage.py#L25) — `require_api_key|def _require|FLOWW_ENABLE_LIVE_PUBLIC`; lines 25, 40, 49, 53, 56, 61, 80, 191, 286, 356, 409, 616, 649, 664
- [backend/routes/llm.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/routes/llm.py#L22) — `_MODEL_ID_RE|_allowed_turboquant_models`; lines 22, 25, 39, 44
- [backend/routes/alphapod_compat.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/routes/alphapod_compat.py#L418) — `FLOWW_ALLOW_DEV_TOKENS|exp.*86400`; lines 418, 421, 425, 447
- [backend/tests/routes/test_public_brokerage_auth.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/routes/test_public_brokerage_auth.py#L45) — `def test_`; lines 45, 49, 53, 57, 72, 83, 90, 119, 138, 146
- [backend/tests/routes/test_rce_guards.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/routes/test_rce_guards.py#L25) — `def test_`; lines 25, 33, 41, 49, 61, 67, 73, 83, 94, 99
- [backend/portfolio.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/portfolio.py#L143) — `aq = abs|delta.*aq`; lines 143, 145
- [backend/services/gex_core.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/gex_core.py#L406) — `gex_unit = dollar_gex_per_contract.gamma, vol`; lines 406, 1018

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/6d44add0587ca5b6372099c2fcc24a573fb1354e

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #52 — fix(r8-finish): green the frontend suite + record post-R8 merges

**Classification: current intent retained**

The Radix is-development production-variant mapping survives in Jest-only config. The historic bizDTE expiry helper itself was superseded: current Blademap test defines a relative Date.now()+14-day expiry and exercises the successor exclusive expiry-band UI. The original fixed September date is not present. Frozen-file authorization and current whole-suite/build health are not inferred from this historic merge.

PR: https://github.com/odaialdajani/floww-2/pull/52
Historical head: https://github.com/odaialdajani/floww-2/commit/5f13958d2cd4b852effd3ed1cdeaa5cf437367d2
Merge: https://github.com/odaialdajani/floww-2/commit/3e24a6231b443863ab09e0921187f7f1519ab97e; ancestor of candidate: True.

API: files: 4 records / 1 pages, commits: 1 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [frontend/craco.config.js](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/craco.config.js#L39) — `is-development`; lines 39, 42, 43
- [frontend/src/components/flowseeker/BlademapFlowView.test.jsx](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/flowseeker/BlademapFlowView.test.jsx#L7) — `const expiry=|drill expiry bands are exclusive`; lines 7, 29

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/5f13958d2cd4b852effd3ed1cdeaa5cf437367d2

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #53 — fix(v3-budget-honesty): budget-exhaustion 429s + kill the contract flake

**Classification: current intent retained**

Both /api/contract paths preserve degraded budget/fetch markers as 429/503 before _check_chain. Current table GEX uses option_type_sign and dollar_gex_per_contract rather than the former S-only expression. Autouse shared-budget reset still brackets costsave tests; dev token TTL remains 86400.

PR: https://github.com/odaialdajani/floww-2/pull/53
Historical head: https://github.com/odaialdajani/floww-2/commit/e65c44e2f24b5d569c9104576c7e29cc44929da8
Merge: https://github.com/odaialdajani/floww-2/commit/71f83625acef8532ac2b20760524b7b241335568; ancestor of candidate: True.

API: files: 5 records / 1 pages, commits: 2 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [backend/routes/analytics.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/routes/analytics.py#L430) — `budget_exhausted|dollar_gex_per_contract`; lines 430, 437, 453, 552
- [backend/tests/test_v3_costsave.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/test_v3_costsave.py#L16) — `def _reset_shared_public_budget`; lines 16
- [backend/tests/test_contract_strike_route.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/test_contract_strike_route.py#L2) — `budget|degraded`; lines 2, 70, 80, 86, 89
- [backend/routes/alphapod_compat.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/routes/alphapod_compat.py#L447) — `exp.*86400`; lines 447

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/cfe0aa371fe0283614c5882dde5bd6000054e50d
- https://github.com/odaialdajani/floww-2/commit/e65c44e2f24b5d569c9104576c7e29cc44929da8

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #54 — fix(trade-ready-wires): alerts overlay on SSE, drop dead hook + stale docs

**Classification: superseded/declined**

Original SSE switch was intentionally withdrawn in follow-up e5712826 after #56 added the WebSocket producer. Final PR only adds AlertOverlay tests, removes the unused snapshot hook and corrects DualGEXBadge documentation. Current component still opens tokenized /ws/signals and reads normalized frames; restoring the old proposed SSE switch would be stale work.

PR: https://github.com/odaialdajani/floww-2/pull/54
Historical head: https://github.com/odaialdajani/floww-2/commit/917fea5db1f6a655b58c5289717879a03ca2aabb
Merge: https://github.com/odaialdajani/floww-2/commit/2333c5bf4e3d58503f4cd311896e5c62a22906d7; ancestor of candidate: True.

API: files: 3 records / 1 pages, commits: 3 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [frontend/src/components/AlertOverlay.js](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/AlertOverlay.js#L3) — `withWsToken|data.type`; lines 3, 151, 163
- [frontend/src/components/AlertOverlay.test.jsx](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/AlertOverlay.test.jsx#L77) — `normalized signal|opens exactly`; lines 77, 85
- [frontend/src/components/heatseeker/DualGEXBadge.jsx](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/DualGEXBadge.jsx#L5) — `BACKEND_BASE|REACT_APP_STEAL`; lines 5, 6, 14, 16

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/48d65bc14253aad6fa2bdbb5669be8cbafb9297d
- https://github.com/odaialdajani/floww-2/commit/e5712826e11e34bfe2f63937f8bf93c08c6f08a2
- https://github.com/odaialdajani/floww-2/commit/917fea5db1f6a655b58c5289717879a03ca2aabb

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #55 — feat(trade-ready): lifecycle persistence + universe scan + conviction rank

**Classification: confirmed repair needed**

Lifecycle serialization/store rehydration, universe routes and leaderboard UI survive. However the actual route producer _universe_scan_conviction returns rank_one output with tier/evidence, then universe_scan feeds that into rank_many. rank_many recognizes tier as fused and discards the blob, recomputing from opportunity alone: a real flow reading is lost. Reproduced with current pure module: flow=100, opportunity=0 yields producer 35.0 / flow_status=ok / flow_alert_key=fixture-flow, then consumer 0.0 / missing / key absent. Confluence/ML are explicitly None at the producer; their unwired state is a disclosed hold, not a new request to invent evidence.

PR: https://github.com/odaialdajani/floww-2/pull/55
Historical head: https://github.com/odaialdajani/floww-2/commit/687a3cd1bc6ea19ba07680ea61b22833a4bcb251
Merge: https://github.com/odaialdajani/floww-2/commit/b9fd5eee21725ace5d53e4dbb8f563fc51452edf; ancestor of candidate: True.

API: files: 16 records / 1 pages, commits: 4 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [backend/routes/flowseeker.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/routes/flowseeker.py#L2623) — `def _universe_scan_conviction|return _rank|fused = _rank_many`; lines 2623, 2641, 2712
- [backend/services/conviction_rank.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/conviction_rank.py#L253) — `def rank_many|fused_markers|flow=flow`; lines 253, 270, 271, 281
- [backend/services/universe_scan.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/universe_scan.py#L170) — `row\[.conviction.\]|def latest_leaderboard`; lines 170, 172, 229
- [backend/server.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/server.py#L1884) — `latest_wall_last_state|record_wall_last_state`; lines 1884, 1894, 1938, 1941, 1945
- [backend/tests/services/test_universe_scan_conviction.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/services/test_universe_scan_conviction.py#L246) — `def test_rank_many_sorts|def test_scan_batch_builds`; lines 246, 284

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/8febc2544977eb63d83ef145c5eadad913e814c4
- https://github.com/odaialdajani/floww-2/commit/580ef4f4d64cc51fcf8b488a2fe2fc7052502ee7
- https://github.com/odaialdajani/floww-2/commit/3136e5dd58c7ca2e22bebb58b311195bfcbab2da
- https://github.com/odaialdajani/floww-2/commit/687a3cd1bc6ea19ba07680ea61b22833a4bcb251

### Reproducible gap / safe failing-test proposal

```json
[
  {
    "id": "FLOW-FUSION-LOSS",
    "severity": "medium",
    "call_path": "GET /api/flowseeker/universe/scan -> scan_batch(conviction_fn=_universe_scan_conviction) -> rank_one -> rank_many -> record_leaderboard",
    "reproduction": {
      "method": "Exact candidate _universe_scan_conviction AST executed with in-memory fake alert feed and pure rank_one module, then exact candidate universe_scan fused-assignment AST executed. No server, broker, store or real feed imported.",
      "producer_conviction": 35.0,
      "producer_flow_status": "ok",
      "producer_flow_key": "fixture-flow",
      "consumer_flow_status": "missing",
      "consumer_flow_key": null,
      "preservation_assertion": false,
      "consumer_before_persistence_conviction": 0.0
    },
    "safe_failing_test_proposal": "Offline test with mocked read_alert_feed=[{conviction:100,key:fixture-flow}], opportunity_score=0 and injected heatmap; exercise scan_batch plus the exact route fusion stage. Assert resulting conviction remains 35.0 and evidence.flow_alert_key survives; current code produces 0.0/missing. Include two-ticker case to prove stronger measured flow can affect ordering. Preserve reject-ambiguous-fused-blob guards: do not reinterpret an aggregate score as raw flow; either sort already-fused rows or pass genuine scorer inputs explicitly."
  }
]
```

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #56 — feat(roadmap): per-strike node confluence overlay + /ws/signals producer + flow-at-node route

**Classification: current intent retained**

node_brief is consumed by the node-confluence route and mounted NodeConfluencePanel. Structure remains context_only, missing dimensions do not count as signed evidence. The signal producer normalizes type=signal with original kind preserved, and exact /ws/signals registration precedes the greedy route. This row inspects primary feature and WS paths; it does not recertify all 18 carried test/CI/durability commits or original human acceptance screenshots.

PR: https://github.com/odaialdajani/floww-2/pull/56
Historical head: https://github.com/odaialdajani/floww-2/commit/c8471a14015c2e9d25028d928e32b24e777c58e0
Merge: https://github.com/odaialdajani/floww-2/commit/51da6f3b3faa5d08a0f558cea2060545c0255585; ancestor of candidate: True.

API: files: 39 records / 1 pages, commits: 18 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [backend/services/node_confluence.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/node_confluence.py#L184) — `def node_brief|context_only|confluence_score`; lines 184, 193, 213, 227, 233
- [backend/routes/heatseeker.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/routes/heatseeker.py#L646) — `node_confluence|node_brief`; lines 646, 667, 718
- [frontend/src/components/heatseeker/HeatseekerDashboard.jsx](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/HeatseekerDashboard.jsx#L100) — `NodeConfluencePanel`; lines 100, 241
- [backend/routes/alerts.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/routes/alerts.py#L133) — `def _signal_frame|broadcast_signal\(alert|verify_ws`; lines 133, 173, 175, 377
- [backend/server.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/server.py#L3884) — `add_api_websocket_route`; lines 3884
- [backend/tests/routes/test_node_confluence_route.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/routes/test_node_confluence_route.py#L52) — `def test_`; lines 52, 67, 82, 88, 98, 112, 120

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/f5c12e185f86a15cdfb1155cedae2eb0fdac7578
- https://github.com/odaialdajani/floww-2/commit/f2a3ee865c0ae101911d7db7fa6d6c548dc0981d
- https://github.com/odaialdajani/floww-2/commit/626839c4a98084206a991c5d2932e64e9bef3e45
- https://github.com/odaialdajani/floww-2/commit/7283d7982a2bde8c74402f5997d586e70d1a5310
- https://github.com/odaialdajani/floww-2/commit/c76171dfdec207212ef1a3523d19ef00226bb0e7
- https://github.com/odaialdajani/floww-2/commit/f5905dc3f18dd043e4f923a0762479b8540ddd3b
- https://github.com/odaialdajani/floww-2/commit/af22c02d22c3440372c8b945d13aa1af6b80e517
- https://github.com/odaialdajani/floww-2/commit/ae821c70dd5e052ccc5f57f161a4778598982a82
- https://github.com/odaialdajani/floww-2/commit/d1ff8162bb7a03d0b7c264fc0010f8f069218ee7
- https://github.com/odaialdajani/floww-2/commit/f0fe42d477d3e2c77445437dc8053e55d9e1afb3
- https://github.com/odaialdajani/floww-2/commit/160838d8616a9297304c8759cccd5dc6abb8b200
- https://github.com/odaialdajani/floww-2/commit/1c3cfa99a9779cced87a5e66f127e2c7a9e36ee8
- https://github.com/odaialdajani/floww-2/commit/6aaa7dea81239d55f96e5b4e5826c2b2e00cdbe8
- https://github.com/odaialdajani/floww-2/commit/1c471b20a879621cdc46e2d19df7f08625662245
- https://github.com/odaialdajani/floww-2/commit/bc47b8d5eaa15504bd987290228d47d63c380fac
- https://github.com/odaialdajani/floww-2/commit/b94397bb798db936bcd99827a180e494a0b5e05e
- https://github.com/odaialdajani/floww-2/commit/473ae1564038e934358ee78331dd302fec5f27c2
- https://github.com/odaialdajani/floww-2/commit/c8471a14015c2e9d25028d928e32b24e777c58e0

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #57 — fix(ci+docs): repair the silent-except gate that never ran, and the API docs nobody could use

**Classification: owner-hold or unverified**

Current Charm producer returns partial/unavailable honestly and server attaches it; inspector reads payload VEX grid. ML route rejects missing/nonfinite feature vectors, and primary alert normalization survived reconciliation instead of old setdefault. Observability/test changes, retirement and API generation are inventoried; this 87-file/23-commit PR is not fully behavior-verified here. Rotation, artifact/training readiness and real monitoring deployment remain unverified; current source cannot be certified by historical suite counts.

PR: https://github.com/odaialdajani/floww-2/pull/57
Historical head: https://github.com/odaialdajani/floww-2/commit/577345c4a7d6cd7e6bea6e330c417b07c90c8a77
Merge: https://github.com/odaialdajani/floww-2/commit/365a9616dfb889d86466c5dfb4ce6f5f912cc38f; ancestor of candidate: True.

API: files: 87 records / 1 pages, commits: 23 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [backend/services/gex_core.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/gex_core.py#L1555) — `def compute_charm_grid_local|PARTIAL_CHARM_COVERAGE`; lines 1555, 1633
- [backend/server.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/server.py#L1117) — `compute_charm_grid_local|charm_grid`; lines 1117, 1120, 1124, 1126, 2738
- [frontend/src/components/heatseeker/WallInspector.jsx](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/WallInspector.jsx#L157) — `vex_grid`; lines 157
- [backend/routes/ml_predict_api.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/routes/ml_predict_api.py#L197) — `feature_schema_mismatch|non_finite_features`; lines 197, 221
- [backend/tests/services/test_charm_grid_surface.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/services/test_charm_grid_surface.py#L25) — `def test_`; lines 25, 37, 46, 60, 70, 78, 84
- [.github/workflows/lint.yml](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/.github/workflows/lint.yml#L21) — `silent|check_silent`; lines 21, 32, 33, 35, 44, 54, 56
- [docker-compose.observability.yml](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/docker-compose.observability.yml#L3) — `3001|./prometheus|./grafana`; lines 3, 13, 18, 19, 20, 22, 35, 45, 48, 52, 53, 59, 60, 61, 62

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/e495b108929b3b944696fbd96a1be59ad6cf66ad
- https://github.com/odaialdajani/floww-2/commit/4a739d577047f5691a7950fa2a1d6d3e82a28909
- https://github.com/odaialdajani/floww-2/commit/41f6997e8fb4cdc39bb6c7f81edc7f253fd442ca
- https://github.com/odaialdajani/floww-2/commit/abb8c488a2abd199b3563597ceb74cdeca6b6521
- https://github.com/odaialdajani/floww-2/commit/c2fa3288a0ee82e5aaf200368376d402e0838c78
- https://github.com/odaialdajani/floww-2/commit/6b45221ef97124741e7027b02102205ed4b33845
- https://github.com/odaialdajani/floww-2/commit/0702e209c17f01ba77d3faf5daac33b1f7ab4aec
- https://github.com/odaialdajani/floww-2/commit/76071fb42434583d3dc5edc780b7c5f9d72b19a1
- https://github.com/odaialdajani/floww-2/commit/0830331574e4ebe6c19f83b5c30e60dcb233ca1b
- https://github.com/odaialdajani/floww-2/commit/9d28b877825002b47041ec4485680d12ad778e2e
- https://github.com/odaialdajani/floww-2/commit/2d5b079801ee682fadbacd831861ce8933c999ea
- https://github.com/odaialdajani/floww-2/commit/4108e425252b3a886a9e1103b50eeef946ad93b2
- https://github.com/odaialdajani/floww-2/commit/563db8db15bee29f20fcd75e626c16ab8a5521fb
- https://github.com/odaialdajani/floww-2/commit/1890d17d56501c3a888512c04ef92b58090f4e22
- https://github.com/odaialdajani/floww-2/commit/18d32551af3a48d30ac860ce83a1ccd860bf1e2c
- https://github.com/odaialdajani/floww-2/commit/e27d3f41425f270a8ef9c841f911c8a742349eeb
- https://github.com/odaialdajani/floww-2/commit/f6f6c7efb411d9cfe6c472279c669598a32663c3
- https://github.com/odaialdajani/floww-2/commit/c00c16b9fcacadee355c4ec15dc926bde5f824f5
- https://github.com/odaialdajani/floww-2/commit/73c1dfd8537781021c962d06dbba8a6f80940926
- https://github.com/odaialdajani/floww-2/commit/fdb940b67d3ec0b45510a82c6d46da401b8dcf34
- https://github.com/odaialdajani/floww-2/commit/7aeb7e848871f136249faa869c90dc70d3f2d169
- https://github.com/odaialdajani/floww-2/commit/ed1b367d800ce219a55503072d05ce2b538b8093
- https://github.com/odaialdajani/floww-2/commit/577345c4a7d6cd7e6bea6e330c417b07c90c8a77

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #58 — docs(solstice): record post-merge state and per-PR merge decisions

**Classification: superseded/declined**

Historical post-merge/hold receipt survives under later corrections. The current STATUS header explicitly retracts the old #57/#3/#4 hold verdicts; do not resurrect them as present defects. Source checks of _signal_frame, exact WS registration and preserved appKey corroborate that those old concerns are not current missing work.

PR: https://github.com/odaialdajani/floww-2/pull/58
Historical head: https://github.com/odaialdajani/floww-2/commit/24c0b3717def36a95c87cbbdf62e952ac50843eb
Merge: https://github.com/odaialdajani/floww-2/commit/d6ed0e0b2695be15b26b3a4c6723508452e34e72; ancestor of candidate: True.

API: files: 1 records / 1 pages, commits: 1 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [docs/solstice/STATUS.md](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/docs/solstice/STATUS.md#L5) — `RESOLVED|Superseded open-PR|#54`; lines 5, 72, 91, 113
- [backend/routes/alerts.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/routes/alerts.py#L133) — `def _signal_frame`; lines 133
- [backend/server.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/server.py#L3884) — `add_api_websocket_route`; lines 3884
- [frontend/src/utils/appKey.js](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/utils/appKey.js#L29) — `export`; lines 29, 45, 54, 64, 74, 85

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/24c0b3717def36a95c87cbbdf62e952ac50843eb

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #59 — docs(solstice): record verified conflict counts and the #54 rebase

**Classification: superseded/declined**

The final #54 payload was actually rebased to retain WebSocket behavior and added tests, matching this receipt. Historical 412-conflict and stale-branch descriptions are dated; current STATUS explicitly supersedes them. No scratch test-merge performed because the audit is read-only and pinned; history/current scope, not old conflict counts, drives verdict.

PR: https://github.com/odaialdajani/floww-2/pull/59
Historical head: https://github.com/odaialdajani/floww-2/commit/bca9c28bbba1ee63b8a0056ec548c50075e25223
Merge: https://github.com/odaialdajani/floww-2/commit/5d92ae012d07903bf1d503e7bada42e7a6940ec1; ancestor of candidate: True.

API: files: 1 records / 1 pages, commits: 3 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [docs/solstice/STATUS.md](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/docs/solstice/STATUS.md#L72) — `RESOLVED|Method note|412 conflicts`; lines 72, 104, 111
- [frontend/src/components/AlertOverlay.js](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/AlertOverlay.js#L151) — `/ws/signals`; lines 151
- [frontend/src/components/AlertOverlay.test.jsx](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/AlertOverlay.test.jsx#L85) — `normalized signal`; lines 85

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/6b81ea56cf550b0688dda3025035945368643a38
- https://github.com/odaialdajani/floww-2/commit/f770d131941ffdaace99b7c23c6da5874941dea6
- https://github.com/odaialdajani/floww-2/commit/bca9c28bbba1ee63b8a0056ec548c50075e25223

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #60 — docs(audit): record unverified artifacts the CI truth audit does not surface

**Classification: owner-hold or unverified**

Read historical audit document and current loader/gate code. The report corrected its own earlier reachability overstatement: fixed direction_v1.0 names are loaded from root models, not a glob over backend/models RF filenames. Gate discovery was subsequently widened by #61. Model quality/retraining/quarantine remains an owner modeling decision; no protected artifact payloads were scanned, loaded, copied or re-evaluated.

PR: https://github.com/odaialdajani/floww-2/pull/60
Historical head: https://github.com/odaialdajani/floww-2/commit/206de221019cf7f9712ef8c7302d55dd452c2302
Merge: https://github.com/odaialdajani/floww-2/commit/89fb61b0d8aed1eda879870bcc8c7d8e180604b1; ancestor of candidate: True.

API: files: 1 records / 1 pages, commits: 2 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [docs/audit/MODEL-AUDIT-2026-09-27.md](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/docs/audit/MODEL-AUDIT-2026-09-27.md#L97) — `NOT on the live|Open question|not evidence`; lines 97
- [backend/ml_price_prediction.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/ml_price_prediction.py#L211) — `model_path.*direction_v1|status.*no_model`; lines 211, 215
- [qc/audit/truth_audit.sh](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/qc/audit/truth_audit.sh#L173) — `manifest|find models backend/models`; lines 173, 175, 180, 182

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/8634efb8329a9ba9cf0d89ae3ab95d8748af3a06
- https://github.com/odaialdajani/floww-2/commit/206de221019cf7f9712ef8c7302d55dd452c2302

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #61 — fix(qc): audit the *_manifest.json descriptors the truth audit was blind to

**Classification: current intent retained**

Descriptor discovery includes *_manifest.json in both root models and backend/models, excluding quarantine. Subject-scoped WARN/FAIL remains deliberate. CI still invokes truth_audit; syntax check this session exits 0. This proves the script path/patterns, not independent validation of any artifact or predictive edge.

PR: https://github.com/odaialdajani/floww-2/pull/61
Historical head: https://github.com/odaialdajani/floww-2/commit/f9275c57fafab5273b681637a0e038e55e47fb0c
Merge: https://github.com/odaialdajani/floww-2/commit/b46e9af037da6377a03f5a19e5032896de0b6e83; ancestor of candidate: True.

API: files: 1 records / 1 pages, commits: 3 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [qc/audit/truth_audit.sh](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/qc/audit/truth_audit.sh#L173) — `MODEL_METAS|manifest|MODEL_RULES_BLOCK`; lines 173, 175, 179, 182, 185, 213, 215, 219, 264, 285, 300, 319
- [.github/workflows/ci.yml](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/.github/workflows/ci.yml#L38) — `run: bash qc/audit/truth_audit.sh`; lines 38
- [backend/tests/test_truth_audit_gate.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/test_truth_audit_gate.py#L207) — `test_manifest_fixtures|test_violation_warns`; lines 207, 249

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/1a44411b1304d414c95f157cad473bb881c855ad
- https://github.com/odaialdajani/floww-2/commit/b846da9c2d416773ff6e23201944e7aefb610c82
- https://github.com/odaialdajani/floww-2/commit/f9275c57fafab5273b681637a0e038e55e47fb0c

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #62 — test(qc): self-test for the truth-audit gate widened in #61

**Classification: current intent retained**

The isolated truth-audit self-test harness remains and now covers all naming conventions, per-rule failure/warning behavior and subject-only triggering. Current version uses platform-aware subprocess wrappers and tracked executable mode checks, superseding some original platform details. Tests create fixtures rather than reading protected model values; reviewed but not executed under the two-output-file-only restriction.

PR: https://github.com/odaialdajani/floww-2/pull/62
Historical head: https://github.com/odaialdajani/floww-2/commit/e9db2910ebddc476d3a2e946aab0bdf5b0893b98
Merge: https://github.com/odaialdajani/floww-2/commit/0eda3d394e68e0328283674e499738fd9a1baffd; ancestor of candidate: True.

API: files: 1 records / 1 pages, commits: 2 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [backend/tests/test_truth_audit_gate.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/test_truth_audit_gate.py#L89) — `def run_gate|REQUIRED_PATTERNS|def test_each_convention|def test_ml_word_in_body`; lines 89, 109, 188, 284, 312
- [qc/audit/truth_audit.sh](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/qc/audit/truth_audit.sh#L46) — `MODEL_RULES_BLOCK|COMMIT_SUBJECT`; lines 46, 50, 55, 70, 72, 212, 213, 215, 219

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/d3636819073f21bb21b9d0d97036ad4227daa3e3
- https://github.com/odaialdajani/floww-2/commit/e9db2910ebddc476d3a2e946aab0bdf5b0893b98

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #63 — fix(agent,compose,api): unblock CI on three independent failures

**Classification: current intent retained**

GroundedModel settlement failure keeps accounted false and reports reserved/actual_cost=None; reconciliation uses usage lookup rather than repeating paid generation. Companion MockTransport tests assert that exact split. Compose consistency now recognizes gitignored build outputs without broadly exempting misspelled mounts. API generator remains deterministic in source; fresh live OpenAPI regeneration was not run.

PR: https://github.com/odaialdajani/floww-2/pull/63
Historical head: https://github.com/odaialdajani/floww-2/commit/d1f5699f49a01f857fbfeb81c566ef99c96c108b
Merge: https://github.com/odaialdajani/floww-2/commit/ba84569927bf1776d628d43c5e33b3aadc4725c3; ancestor of candidate: True.

API: files: 5 records / 1 pages, commits: 3 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [backend/services/agent/model.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/agent/model.py#L212) — `accounted = True|actual_cost=actual if accounted|accounting=|async def reconcile`; lines 212, 216, 226, 227, 272
- [backend/tests/agent/test_settlement_failure_path.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/agent/test_settlement_failure_path.py#L79) — `failed_settlement|MockTransport`; lines 79, 101
- [backend/tests/test_compose_consistency.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/test_compose_consistency.py#L66) — `def _is_ignored_build_output|if _is_ignored`; lines 66, 106
- [qc/audit/generate_api_docs.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/qc/audit/generate_api_docs.py#L88) — `sort_keys=True|def render_readme`; lines 88, 133

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/4e404465a686f30c56dc51311226f7e3c5e2f47f
- https://github.com/odaialdajani/floww-2/commit/f8c1a92d9094a9fdff027c964f46b6f0106283e3
- https://github.com/odaialdajani/floww-2/commit/d1f5699f49a01f857fbfeb81c566ef99c96c108b

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #64 — docs(solstice): refresh the header to ba845699 and record two retractions

**Classification: superseded/declined**

Historical status refresh/retractions persist, but its ba845699 snapshot and counts are superseded by later STATUS revisions. The substantive retractions remain: old #57 channel concern was resolved and RF artifacts were not proven live solely by directory. Does not prove current suite totals or model health.

PR: https://github.com/odaialdajani/floww-2/pull/64
Historical head: https://github.com/odaialdajani/floww-2/commit/fd0e7835c66679494dd216f707932e2b74b48cd9
Merge: https://github.com/odaialdajani/floww-2/commit/37488ddb4eb015e81c4dc39eae4ee8e2d39dbf51; ancestor of candidate: True.

API: files: 1 records / 1 pages, commits: 1 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [docs/solstice/STATUS.md](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/docs/solstice/STATUS.md#L23) — `earlier entry is retracted|RESOLVED|truth-audit claim count`; lines 23, 61, 72
- [backend/ml_price_prediction.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/ml_price_prediction.py#L211) — `direction_v1.0.joblib`; lines 211
- [backend/routes/alerts.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/routes/alerts.py#L133) — `def _signal_frame`; lines 133

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/fd0e7835c66679494dd216f707932e2b74b48cd9

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #65 — docs: restore the CLAUDE.md venv fix that a side-branch recovery reverted

**Classification: current intent retained**

CLAUDE working-interpreter note now distinguishes backend/.venv from the shipped 3.12 pin; current Docker/CI pins are the authority. Machine-specific historical command blocks remain mixed and should not be executed blindly in this clean worktree, which intentionally has no local venv. No service launch or machine-path acceptance inferred.

PR: https://github.com/odaialdajani/floww-2/pull/65
Historical head: https://github.com/odaialdajani/floww-2/commit/a25af48b6769717427bac6cd7737be9fb75c9815
Merge: https://github.com/odaialdajani/floww-2/commit/ac2b8ef9dcbaa06d38ef00fb39109f4a38e6e5fa; ancestor of candidate: True.

API: files: 1 records / 1 pages, commits: 1 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [CLAUDE.md](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/CLAUDE.md#L3) — `Version skew trap|working interpreter|Environment note`; lines 3, 173, 216, 267
- [Dockerfile.backend](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/Dockerfile.backend#L1) — `FROM python`; lines 1
- [.github/workflows/ci.yml](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/.github/workflows/ci.yml#L45) — `python-version`; lines 45, 48

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/a25af48b6769717427bac6cd7737be9fb75c9815

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #66 — docs(solstice): mark #3, #4 and #57 resolved, and correct three stale counts

**Classification: superseded/declined**

The corrected current-vs-historical #3/#4/#57 disposition is still present and old do-not-merge lines explicitly retained as superseded history. Source confirms appKey exists and exact WS registration/normalization survive. Historical numerical counts are not candidate proof.

PR: https://github.com/odaialdajani/floww-2/pull/66
Historical head: https://github.com/odaialdajani/floww-2/commit/d32e827082e8aa72568d9e7955e20beefc223919
Merge: https://github.com/odaialdajani/floww-2/commit/f77b87dd97cf3a87c3e7c12ed16087ebd079b3ed; ancestor of candidate: True.

API: files: 1 records / 1 pages, commits: 1 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [docs/solstice/STATUS.md](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/docs/solstice/STATUS.md#L72) — `RESOLVED|verdicts were right|Superseded open-PR`; lines 72, 88, 91
- [frontend/src/utils/appKey.js](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/utils/appKey.js#L29) — `export`; lines 29, 45, 54, 64, 74, 85
- [backend/routes/market_data.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/routes/market_data.py#L209) — `fetched_at.*received_at`; lines 209

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/d32e827082e8aa72568d9e7955e20beefc223919

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #67 — chore(gitignore): cover the SQLite runtime stores the duckdb rules missed

**Classification: current intent retained**

Root and backend runtime-store ignore patterns survive for DuckDB/SQLite/db plus sidecars. Read-only git check-ignore --no-index with three synthetic paths matched backend sqlite3, its WAL and root DuckDB; no actual data store was read or created.

PR: https://github.com/odaialdajani/floww-2/pull/67
Historical head: https://github.com/odaialdajani/floww-2/commit/8e9ffe1728e4706ded61a71f85829a969dc38146
Merge: https://github.com/odaialdajani/floww-2/commit/69d73c958d40a245a9fe89ca816b9ee9e5500bd2; ancestor of candidate: True.

API: files: 1 records / 1 pages, commits: 1 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [.gitignore](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/.gitignore#L132) — `backend/data/.*sqlite3|data/.*duckdb|backend/data/.*db`; lines 132, 134, 138, 139, 140, 145, 146, 147, 148, 149, 150, 151, 152, 153

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/8e9ffe1728e4706ded61a71f85829a969dc38146

**Depth/limits:** Historical full one-file patch and current ignore definitions read; git check-ignore exit 0. No data scan or store modification.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #68 — fix(requirements,test): make @pytest.mark.flaky functional and seed the test that flaked

**Classification: current intent retained**

pytest-rerunfailures remains in requirements and the overfit-small-dataset test seeds Torch before input/model creation. Current CI installs the requirements file, so plugin availability is not merely a comment. No dependency install, training or repeated stochastic run was done during this read-only audit.

PR: https://github.com/odaialdajani/floww-2/pull/68
Historical head: https://github.com/odaialdajani/floww-2/commit/a56059b6a13cdfa86445a9f0175f981513b375d6
Merge: https://github.com/odaialdajani/floww-2/commit/29bddf85a320cf364c458493503f5787ee542784; ancestor of candidate: True.

API: files: 2 records / 1 pages, commits: 2 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [backend/requirements.txt](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/requirements.txt#L55) — `pytest-rerunfailures`; lines 55
- [backend/tests/services/test_anomaly_training.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/services/test_anomaly_training.py#L159) — `def test_overfit_small_dataset|manual_seed`; lines 159, 169
- [.github/workflows/ci.yml](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/.github/workflows/ci.yml#L66) — `pip install -r requirements.txt`; lines 66

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/a7802f2a547a2a7d9664a5e048139a10c3a5c8e0
- https://github.com/odaialdajani/floww-2/commit/a56059b6a13cdfa86445a9f0175f981513b375d6

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #69 — docs(solstice): correct three stale STATUS claims, including a metric that had no fixed value

**Classification: superseded/declined**

STATUS retains the rationale that truth-audit count depends on commit claims, plus corrections on ignore rules, mutation coverage and seeded tests. Later #72 stops pinning the changing main SHA. Historical totals are receipts only, not current engineering proof.

PR: https://github.com/odaialdajani/floww-2/pull/69
Historical head: https://github.com/odaialdajani/floww-2/commit/26307bc61e9f0d80fcd2ce287f2cf24eb9b634fb
Merge: https://github.com/odaialdajani/floww-2/commit/5dcb8774eb96fe18f179805e89498ddc884d9caf; ancestor of candidate: True.

API: files: 1 records / 1 pages, commits: 2 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [docs/solstice/STATUS.md](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/docs/solstice/STATUS.md#L23) — `truth-audit claim count|#68 added|#70 mutation|#69 is`; lines 23, 42, 47, 52
- [qc/audit/truth_audit.sh](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/qc/audit/truth_audit.sh#L46) — `COMMIT_SUBJECT`; lines 46, 50, 55, 70, 72, 212

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/15fae25ab58ac9a5a1480743922cb0160b60f5f6
- https://github.com/odaialdajani/floww-2/commit/26307bc61e9f0d80fcd2ce287f2cf24eb9b634fb

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #70 — test(market-data): pin the positivity and volume halves of the completed-session bar guard

**Classification: current intent retained**

Five invalid low/volume/nonfinite cases remain against the actual Public completed-session-close seam; producer requires strictly positive low, ordered OHLC and nonnegative volume. Source path is current, not an invented missing old module. Reviewed tests are not fresh network/provider acceptance.

PR: https://github.com/odaialdajani/floww-2/pull/70
Historical head: https://github.com/odaialdajani/floww-2/commit/2d653eb2387c9a3079b83855ee04426390069022
Merge: https://github.com/odaialdajani/floww-2/commit/70265385dd2bc9f0edb0f7a574b5566f6a60a3ec; ancestor of candidate: True.

API: files: 1 records / 1 pages, commits: 1 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [backend/tests/services/test_live_app_repairs.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/services/test_live_app_repairs.py#L46) — `test_implausible_bar_fields_fail_closed`; lines 46
- [backend/services/public_session_close.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/public_session_close.py#L14) — `0 < bar\[.l.\]|async def completed_public_close`; lines 14, 47
- [backend/services/public_api_adapter.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/public_api_adapter.py#L325) — `completed_public_close`; lines 325, 326, 1478, 1479

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/2d653eb2387c9a3079b83855ee04426390069022

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #71 — docs(solstice): point the STATUS header at the final main SHA and record #69

**Classification: superseded/declined**

This SHA-repointing documentation change was intentionally superseded by #72 because its own merge instantly invalidated the claimed main SHA. Current STATUS preserves the test-count change explanations, not the transient final-main claim.

PR: https://github.com/odaialdajani/floww-2/pull/71
Historical head: https://github.com/odaialdajani/floww-2/commit/b9505ea4463d19214a600822cbb821d8aa4f3865
Merge: https://github.com/odaialdajani/floww-2/commit/95173000a15cd0234d12a5a7bc48d1c071799993; ancestor of candidate: True.

API: files: 1 records / 1 pages, commits: 1 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [docs/solstice/STATUS.md](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/docs/solstice/STATUS.md#L5) — `SHA is deliberately not pinned|#71|#69 is`; lines 5, 7, 9, 52

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/b9505ea4463d19214a600822cbb821d8aa4f3865

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #72 — docs(solstice): stop pinning a SHA that the document own merge invalidates

**Classification: current intent retained**

Current STATUS explicitly avoids a self-invalidating SHA and instructs readers to query the ref. The file is headed 27 Sep and its counts are historical; this audit does not reuse them as candidate or runtime acceptance.

PR: https://github.com/odaialdajani/floww-2/pull/72
Historical head: https://github.com/odaialdajani/floww-2/commit/4365771ffcfe03aeda4393716ed16b1b8bc1a968
Merge: https://github.com/odaialdajani/floww-2/commit/d905c9d238cc958eefdbb495c0831f723ca29de4; ancestor of candidate: True.

API: files: 1 records / 1 pages, commits: 1 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [docs/solstice/STATUS.md](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/docs/solstice/STATUS.md#L3) — `SHA is deliberately not pinned|Cumulative verification|Current state`; lines 3, 7, 12

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/4365771ffcfe03aeda4393716ed16b1b8bc1a968

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #73 — fix: fail closed and correct time/DST handling across 9 sites

**Classification: confirmed repair needed**

Fail-closed budget branches, nullable zone policy, evidence scope allowlist, DTE forwarding, symmetric missing-safe scorers and cross-batch ordering survive in candidate. Original final claim that cursor rotated was subsequently corrected by #86 (prefilter now returns full eligible list). However its anti-refusion guard still drops actual producer flow evidence at the route second fusion stage; see shared FLOW-FUSION-LOSS reproduction on #55. Confluence/ML remain explicitly unavailable rather than silently connected. Friday-pin normal ZoneInfo conversion is present, but fallback still hardcodes UTC-5; no active production caller was found in the inspected strategy/routes scope, so not promoted to a live-execution finding.

PR: https://github.com/odaialdajani/floww-2/pull/73
Historical head: https://github.com/odaialdajani/floww-2/commit/a65f6a3a0f54f30718cede483bf99a003a556f25
Merge: https://github.com/odaialdajani/floww-2/commit/433d99abf01917e6bd56db08a78665fb976ab22f; ancestor of candidate: True.

API: files: 18 records / 1 pages, commits: 40 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [backend/services/conviction_rank.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/conviction_rank.py#L161) — `def rank_many|fused_markers|def _recency`; lines 161, 253, 270, 271
- [backend/routes/flowseeker.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/routes/flowseeker.py#L2641) — `return _rank|fused = _rank_many`; lines 2641, 2712
- [backend/services/universe_scan.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/universe_scan.py#L138) — `BUDGET_UNAVAILABLE|dte=dte|global_rows`; lines 138, 151, 251, 256
- [backend/services/fetch_coordinator.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/fetch_coordinator.py#L125) — `budget_unavailable`; lines 125
- [backend/services/episode_policy.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/episode_policy.py#L83) — `missing_or_malformed_zone`; lines 83
- [backend/services/solstice_evidence.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/solstice_evidence.py#L24) — `_EXPORTABLE_SCOPE_KEYS`; lines 24, 131
- [backend/services/strategies/friday_pin.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/strategies/friday_pin.py#L114) — `ts.astimezone|timedelta.hours=5`; lines 114, 117
- [backend/tests/services/test_conviction_missing_inputs.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/services/test_conviction_missing_inputs.py#L36) — `def test_`; lines 36, 54, 62, 77, 97, 107, 131, 144, 170, 192, 212, 233, 239, 245, 270, 288, 300, 336, 344, 354

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/5cba1d9dc066dc5b8dd41e30802df1721f29b9f5
- https://github.com/odaialdajani/floww-2/commit/57b7342da673519e35426f1604cf74335ede003e
- https://github.com/odaialdajani/floww-2/commit/df3ddc109dbb8a668ef2162df919172473b9e5bc
- https://github.com/odaialdajani/floww-2/commit/b3874cc9989950b1018d60bddc8bd90c9e302256
- https://github.com/odaialdajani/floww-2/commit/b51ee58123230a43fa18fe11a6ceecba2221dc84
- https://github.com/odaialdajani/floww-2/commit/8b291d4445b8c898e5b84ff7461a807f7b89aa75
- https://github.com/odaialdajani/floww-2/commit/32d1d6a3cd82df84fc232a83e27845ead3174441
- https://github.com/odaialdajani/floww-2/commit/d2c87b1e8b1d45da00561f6e76cf841f9f4d0598
- https://github.com/odaialdajani/floww-2/commit/f76a5cee91ea77b6de4690c8a925ab852ae0483c
- https://github.com/odaialdajani/floww-2/commit/e32fed484d2baefd6b3ff2eeecc511130e868802
- https://github.com/odaialdajani/floww-2/commit/13b952bc8650809dba5c84450a221ac329a73059
- https://github.com/odaialdajani/floww-2/commit/91881cc29cebcb82a0afd1e485d013d797ec8fa4
- https://github.com/odaialdajani/floww-2/commit/f7ded485296dba603fda5d90b8cbcb730495671d
- https://github.com/odaialdajani/floww-2/commit/a3d37619c539a59cfd69bc9526adacd241e6a0d5
- https://github.com/odaialdajani/floww-2/commit/e9410de5705a6dfbdee8ccdd486b7e816bb4815f
- https://github.com/odaialdajani/floww-2/commit/c34824bf27c28fe1970f51c30b0c5960acb93c5a
- https://github.com/odaialdajani/floww-2/commit/ec456dc2042fe89e59dc462bcb952b43139a46ab
- https://github.com/odaialdajani/floww-2/commit/38d8a9d1afeb0a3f991a181e19eb635827df7c2e
- https://github.com/odaialdajani/floww-2/commit/f3d916252a7c65fead7b6daf66429fd1fc023b42
- https://github.com/odaialdajani/floww-2/commit/84b11e5effff4832213c5124999d27bdd88efb51
- https://github.com/odaialdajani/floww-2/commit/58ac742cef45b8b742832d085da380d0c1671835
- https://github.com/odaialdajani/floww-2/commit/1814461dc594c9a9f4d61dc810a2fbc945b7ccdb
- https://github.com/odaialdajani/floww-2/commit/1e24f0c03e4ac1ce8f3891f1c101f676335bd055
- https://github.com/odaialdajani/floww-2/commit/f9f73862d1857d232450c949f4517741a94e46a4
- https://github.com/odaialdajani/floww-2/commit/9a6701b8ecf9d4de3c1d9b30513d7e94a69696d0
- https://github.com/odaialdajani/floww-2/commit/244a6b95d11fed747578387057bf07f0b5b7b7f8
- https://github.com/odaialdajani/floww-2/commit/6dbe0bf3534fe8e005865611a5378776f9f7bc03
- https://github.com/odaialdajani/floww-2/commit/decee176bdba05f2e3a2d479d06cef0be287cfda
- https://github.com/odaialdajani/floww-2/commit/ed58eb7c5534b6c91bb85e194b69d59f533776df
- https://github.com/odaialdajani/floww-2/commit/258b81693ce1696910ab3b07e9a106655864be92
- https://github.com/odaialdajani/floww-2/commit/62b571f196fad072b8b017896b6174b165c08d5c
- https://github.com/odaialdajani/floww-2/commit/b0178e6d6971d60f07f5d027fd345e5c1c5e3a88
- https://github.com/odaialdajani/floww-2/commit/a134820ebc0cfa136e2d42a30c438cf6972ec1e5
- https://github.com/odaialdajani/floww-2/commit/68f3f21632d39386a1b6c3429b12840fe3476630
- https://github.com/odaialdajani/floww-2/commit/e9d71a250fa1a3bb34ef2c58cb1c6edf77bae59e
- https://github.com/odaialdajani/floww-2/commit/d5b13041a1d99112ea471e148591b535dd4a0bec
- https://github.com/odaialdajani/floww-2/commit/0c7691a35e6757252a4ed0fbb6bede16dc2af57d
- https://github.com/odaialdajani/floww-2/commit/9bb7307a3a5a6a257b804e1dba06b082f78eb6c0
- https://github.com/odaialdajani/floww-2/commit/1d79a248fb86bc8af22ae36c865bc6473bd5fb40
- https://github.com/odaialdajani/floww-2/commit/a65f6a3a0f54f30718cede483bf99a003a556f25

### Reproducible gap / safe failing-test proposal

```json
[
  {
    "id": "FLOW-FUSION-LOSS",
    "duplicate_of_pr": 55,
    "reproduction": {
      "method": "Exact candidate _universe_scan_conviction AST executed with in-memory fake alert feed and pure rank_one module, then exact candidate universe_scan fused-assignment AST executed. No server, broker, store or real feed imported.",
      "producer_conviction": 35.0,
      "producer_flow_status": "ok",
      "producer_flow_key": "fixture-flow",
      "consumer_flow_status": "missing",
      "consumer_flow_key": null,
      "preservation_assertion": false,
      "consumer_before_persistence_conviction": 0.0
    },
    "safe_failing_test_proposal": "Offline test with mocked read_alert_feed=[{conviction:100,key:fixture-flow}], opportunity_score=0 and injected heatmap; exercise scan_batch plus the exact route fusion stage. Assert resulting conviction remains 35.0 and evidence.flow_alert_key survives; current code produces 0.0/missing. Include two-ticker case to prove stronger measured flow can affect ordering. Preserve reject-ambiguous-fused-blob guards: do not reinterpret an aggregate score as raw flow; either sort already-fused rows or pass genuine scorer inputs explicitly."
  }
]
```

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #74 — feat(solstice-o1o2+triad-o4): layout ownership, Solstice simplify, contract-driven Triad

**Classification: current intent retained**

Current dashboard measures the parent box for fitRows, owns family/basis controls and mounts review drawer; Triad consumes versioned /heatmap snapshots, mapSurface raw/adjusted pair and useReviewJournal instead of obsolete chain-side mapper. Successor UI substantially extends review/selection/replay; current source/test proof is not current browser layout or original owner acceptance.

PR: https://github.com/odaialdajani/floww-2/pull/74
Historical head: https://github.com/odaialdajani/floww-2/commit/28bd60ee9814dc8fe42beb5bd9f432afdef84bf3
Merge: https://github.com/odaialdajani/floww-2/commit/29f74d8a4f1946e9a5d70fabb12a7108c84375f8; ancestor of candidate: True.

API: files: 15 records / 1 pages, commits: 2 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [frontend/src/components/heatseeker/SkylitDashboard.jsx](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/SkylitDashboard.jsx#L23) — `ResizeObserver|setFitRows|ReviewInspector`; lines 23, 379, 381, 386, 403, 406, 410, 1140
- [frontend/src/components/heatseeker/SkylitControlBar.jsx](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/SkylitControlBar.jsx#L138) — `GEX basis|Charm`; lines 138, 144, 159, 166
- [frontend/src/components/TrinityView.jsx](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/TrinityView.jsx#L5) — `/heatmap/|mapSurface|useReviewJournal`; lines 5, 7, 25, 162, 200, 201, 279
- [frontend/src/components/triad/useReviewJournal.js](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/triad/useReviewJournal.js#L12) — `export function|snapshotId`; lines 12, 22, 39, 41, 51
- [frontend/src/components/TrinityView.test.jsx](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/TrinityView.test.jsx#L78) — `renders backend packet|raw and adjusted|handoff selects`; lines 78, 92, 107

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/e2fe3df44ad8d8f7e1762def3125b1dd6c22faae
- https://github.com/odaialdajani/floww-2/commit/28bd60ee9814dc8fe42beb5bd9f432afdef84bf3

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #75 — fix(solstice-o2): remove duplicate family tabs from App filter panel

**Classification: superseded/declined**

Duplicate App family row remains removed; Solstice control bar owns family changes. Original WallPricePath painted the current wall zone across historical closes; successor deliberately removes that misleading history overlay, uses actual timestamps, gaps and a separate current-map reference. Price history remains read-only and replay does not request fresh history. The old shaded-zone screenshot is not an acceptance target to restore.

PR: https://github.com/odaialdajani/floww-2/pull/75
Historical head: https://github.com/odaialdajani/floww-2/commit/00d41fd51c1617ec9b6a07d11101c0c3bd76bf52
Merge: https://github.com/odaialdajani/floww-2/commit/b2e7faec16fc65b445d5c219d7488d1cf1938706; ancestor of candidate: True.

API: files: 5 records / 1 pages, commits: 4 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [frontend/src/App.js](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/App.js#L894) — `family switching|duplicate row`; lines 894, 895
- [frontend/src/components/TrinityView.jsx](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/TrinityView.jsx#L551) — `function WallPricePath|not historical candle-time|Replay: fresh price history`; lines 551, 561, 605, 612
- [frontend/src/components/TrinityView.test.jsx](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/TrinityView.test.jsx#L179) — `current wall is not painted|selected wall keeps actual|no price candles`; lines 179, 191, 223

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/1cb71837dfd073ff4d2813e673038522364433fd
- https://github.com/odaialdajani/floww-2/commit/3a9f48e753cb88a9954c1343f91166a48e756b9c
- https://github.com/odaialdajani/floww-2/commit/e1a5ae93719ca9443f3a5d91b6150169b4ff7563
- https://github.com/odaialdajani/floww-2/commit/00d41fd51c1617ec9b6a07d11101c0c3bd76bf52

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #76 — docs(planning): record PR #73 as merged

**Classification: current intent retained**

Historical ledger records #73 squash/merge identity and head-guard rationale. Actual #73 merge is in candidate ancestry; its historical test run is not reused as fresh verification. Later ledger corrections and unresolved handoff fields remain intact.

PR: https://github.com/odaialdajani/floww-2/pull/76
Historical head: https://github.com/odaialdajani/floww-2/commit/7ea3dc3dfe59d67410e80bd32207b260752e93cd
Merge: https://github.com/odaialdajani/floww-2/commit/b9c5db59bc9548750e29147a12df6c1c344b1ce8; ancestor of candidate: True.

API: files: 1 records / 1 pages, commits: 1 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [.planning/INTEGRATION_H0_H7.md](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/.planning/INTEGRATION_H0_H7.md#L768) — `#73 MERGED|a65f6a3a|head-guard`; lines 768
- [backend/services/conviction_rank.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/conviction_rank.py#L270) — `fused_markers`; lines 270, 271

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/7ea3dc3dfe59d67410e80bd32207b260752e93cd

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #77 — fix(truth-audit): match the subject line, not the whole commit message

**Classification: current intent retained**

Rules 1/2 and model-claim triggers use COMMIT_SUBJECT, avoiding body prose false positives. Refactor subject rule remains active; script passes bash -n this session. Existing gate self-tests exercise subject/body distinctions, but no synthetic git commits were created under read-only scope.

PR: https://github.com/odaialdajani/floww-2/pull/77
Historical head: https://github.com/odaialdajani/floww-2/commit/73d5ed3fc0775287e19f6670219c187e21c86343
Merge: https://github.com/odaialdajani/floww-2/commit/e5195331711313c9c868b37e6e5051c07c5a28e0; ancestor of candidate: True.

API: files: 1 records / 1 pages, commits: 3 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [qc/audit/truth_audit.sh](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/qc/audit/truth_audit.sh#L46) — `COMMIT_SUBJECT|refactor\|Phase A`; lines 46, 50, 55, 70, 72, 212
- [backend/tests/test_truth_audit_gate.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/test_truth_audit_gate.py#L68) — `def test_ml_word_in_body|DOCS_SUBJECT`; lines 68, 256, 270, 278, 284, 302

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/7ea3dc3dfe59d67410e80bd32207b260752e93cd
- https://github.com/odaialdajani/floww-2/commit/7c02a57969b5f4ad36f076aa2b37cb82c5249645
- https://github.com/odaialdajani/floww-2/commit/73d5ed3fc0775287e19f6670219c187e21c86343

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #78 — docs(planning): close out H2-H6; all merged, main green

**Classification: owner-hold or unverified**

This is historical H2–H6 close-out, not current whole-product acceptance. Current ledger itself preserves unresolved handoff/Muse/restart notes and later corrections; stale PID statements cannot establish today’s services. Current engineering has the nine code slices, with the flow-loss counterexample independently recorded here. H5/H7, real Muse connection, durable outcome volume and human acceptance were not commissioned by this audit.

PR: https://github.com/odaialdajani/floww-2/pull/78
Historical head: https://github.com/odaialdajani/floww-2/commit/cd9013a53da70f2f2100d973d233ee059c0699fa
Merge: https://github.com/odaialdajani/floww-2/commit/45b418f22ef524cf9bb485ec06af72783a63408b; ancestor of candidate: True.

API: files: 1 records / 1 pages, commits: 1 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [.planning/INTEGRATION_H0_H7.md](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/.planning/INTEGRATION_H0_H7.md#L517) — `#73 MERGED|Muse connection: NOT|NOT STARTED|NOT DONE|ledger was stale`; lines 517, 768, 775, 776, 809
- [backend/services/solstice_evidence.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/solstice_evidence.py#L24) — `_EXPORTABLE_SCOPE_KEYS`; lines 24, 131

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/cd9013a53da70f2f2100d973d233ee059c0699fa

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #79 — fix(alerts): a boolean was broadcast as a bearish momentum alert

**Classification: current intent retained**

_parse_momentum_score explicitly refuses booleans and malformed input with the documented dead-band 50 sentinel. Exact candidate function executed in memory: True/False/None/garbage -> 50, valid 85 ->85 and 10 ->10. Actual add_snapshot path still feeds alert engine then broadcast_signal; the sentinel is not relabeled measured neutrality.

PR: https://github.com/odaialdajani/floww-2/pull/79
Historical head: https://github.com/odaialdajani/floww-2/commit/a6bfa414b472bacd5d533c92532d0bc48c2fdc05
Merge: https://github.com/odaialdajani/floww-2/commit/0cc9b6c906dff18a2ee6c008a5b40a1a25f98f3c; ancestor of candidate: True.

API: files: 2 records / 1 pages, commits: 1 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [backend/routes/alerts.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/routes/alerts.py#L42) — `def _parse_momentum_score|momentum_score|broadcast_signal\(alert`; lines 42, 329, 334, 368, 369, 377
- [backend/tests/routes/test_alert_plumbing.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/routes/test_alert_plumbing.py#L70) — `test_booleans|test_missing_and_malformed`; lines 70, 89

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/a6bfa414b472bacd5d533c92532d0bc48c2fdc05

**Depth/limits:** Candidate function body extracted with AST and executed on synthetic scalars; related source/tests read. No endpoint or real signal broadcast run.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #80 — docs(planning): record the #79 bool-coercion alert fix

**Classification: current intent retained**

Ledger records the historical bool-coercion alert fix and sentinel limitation; candidate parser and regression tests still match that narrow claim. Historical live-probe statements in this document are not fresh runtime evidence.

PR: https://github.com/odaialdajani/floww-2/pull/80
Historical head: https://github.com/odaialdajani/floww-2/commit/6266f89e4582c81b213cbc8926dc0f892a345b9b
Merge: https://github.com/odaialdajani/floww-2/commit/39b83354bad7c64321a1dbe2726f83ac26f6c9b5; ancestor of candidate: True.

API: files: 1 records / 1 pages, commits: 1 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [.planning/INTEGRATION_H0_H7.md](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/.planning/INTEGRATION_H0_H7.md#L770) — `#79 MERGED|50.*fallback|50.*SENTINEL`; lines 770
- [backend/routes/alerts.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/routes/alerts.py#L55) — `isinstance.raw, bool`; lines 55
- [backend/tests/routes/test_alert_plumbing.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/routes/test_alert_plumbing.py#L70) — `test_booleans`; lines 70

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/6266f89e4582c81b213cbc8926dc0f892a345b9b

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #81 — fix(triad-o5): drawer focus ownership on open and restore on close

**Classification: current intent retained**

Both current drawers capture activeElement, focus close control on open, and restore prior focus in cleanup. Associated focus tests survive successor shared inspector wiring. The backend-only incidental change remains a budget reset in the test seam, not a production behavior waiver. Actual browser focus/mobile interactions were not exercised.

PR: https://github.com/odaialdajani/floww-2/pull/81
Historical head: https://github.com/odaialdajani/floww-2/commit/9c161a6a268a91103bff85716890f2ae69a88a73
Merge: https://github.com/odaialdajani/floww-2/commit/ff879f3a3e52ba7708c14e11a0d4db8f9155fb45; ancestor of candidate: True.

API: files: 5 records / 1 pages, commits: 2 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [frontend/src/components/heatseeker/SkylitDashboard.jsx](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/SkylitDashboard.jsx#L317) — `drawerPrevFocusRef|drawerCloseRef`; lines 317, 318, 321, 322, 324, 1134
- [frontend/src/components/TrinityView.jsx](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/TrinityView.jsx#L124) — `drawerPrevFocusRef|drawerCloseRef`; lines 124, 125, 128, 129, 131, 395
- [frontend/src/components/heatseeker/SkylitDashboard.test.jsx](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/SkylitDashboard.test.jsx#L1275) — `drawer moves focus`; lines 1275
- [frontend/src/components/TrinityView.test.jsx](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/TrinityView.test.jsx#L256) — `drawer moves focus`; lines 256
- [backend/tests/solstice/test_r7_1_red.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/solstice/test_r7_1_red.py#L182) — `budget.reset|budget.*reset|_reset_state`; lines 182, 183, 188

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/940fb5c59f57a3dc8c5c8d0cb0a36964f5541a54
- https://github.com/odaialdajani/floww-2/commit/9c161a6a268a91103bff85716890f2ae69a88a73

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #82 — fix(observability): the health endpoint 500'd during exactly the outages it exists to report

**Classification: current intent retained**

ProviderStats never-success is None; check_alerts still emits provider_down when attempts exist, and JSON-facing health uses nullable elapsed while Prometheus alone gets +inf. SABR/SVI insufficient fit returns rmse=None with fit_status; market_bars test reset clears shared budget/cooldowns. Outage/strict-JSON and broker-seam tests survive. No runtime health request or model fitting was run; the claimed historical 75-request leak prevention is not a fresh whole-suite network-leak proof.

PR: https://github.com/odaialdajani/floww-2/pull/82
Historical head: https://github.com/odaialdajani/floww-2/commit/6487b85be30fceff33f1c1a72b18e394ec667630
Merge: https://github.com/odaialdajani/floww-2/commit/79bf91900db8898fba6081d3f4db81038ecbadb5; ancestor of candidate: True.

API: files: 8 records / 1 pages, commits: 5 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [backend/services/meta_observability.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/meta_observability.py#L261) — `seconds_since_last_success|since is None|float\(.inf.\)`; lines 261, 307, 310, 409, 410, 418, 458, 459, 485, 490
- [backend/services/stochastic_vol.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/stochastic_vol.py#L156) — `rmse.*None|fit_status`; lines 156, 157, 172, 173, 216, 220, 342, 343, 359, 360, 403, 407, 580, 581
- [backend/services/market_bars.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/market_bars.py#L53) — `def _reset_state|_shared_budget.reset`; lines 53, 69
- [backend/tests/routes/test_data_health_outage.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/routes/test_data_health_outage.py#L57) — `def test_`; lines 57, 68, 81, 96
- [backend/tests/services/test_market_bars_reset_state.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/services/test_market_bars_reset_state.py#L66) — `def test_|async def test_`; lines 66, 84, 97

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/6266f89e4582c81b213cbc8926dc0f892a345b9b
- https://github.com/odaialdajani/floww-2/commit/8300af1645e124cf11918812985d4afa9f294d19
- https://github.com/odaialdajani/floww-2/commit/8fada0d60d0b6bafd38391deda479b628ef82302
- https://github.com/odaialdajani/floww-2/commit/c4bdc5fb0dfab80633f771e1864a487e395eb92d
- https://github.com/odaialdajani/floww-2/commit/6487b85be30fceff33f1c1a72b18e394ec667630

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #83 — test(movers): fix a fixture that failed ~70% of calendar days

**Classification: current intent retained**

Current _bars_for takes last/prior from completed_session_pair rather than yesterday-minus-calendar-days and route test still mocks get_daily_bars. This fixes temporal fixture ownership without changing the production Movers policy. The original 200-date statistic was not recomputed and is not used as fresh proof.

PR: https://github.com/odaialdajani/floww-2/pull/83
Historical head: https://github.com/odaialdajani/floww-2/commit/78143ef867e5a858f64294b0ac0c0545ced89240
Merge: https://github.com/odaialdajani/floww-2/commit/f4ced19aabd6acd26ec3feb000f014e099b2233d; ancestor of candidate: True.

API: files: 1 records / 1 pages, commits: 5 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [backend/tests/test_movers_route.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/test_movers_route.py#L19) — `def _bars_for|completed_session_pair|patch\(.services.market_bars`; lines 19, 37, 39, 67
- [backend/services/movers.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/movers.py#L76) — `def completed_session_pair|async def get_movers`; lines 76, 317

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/6266f89e4582c81b213cbc8926dc0f892a345b9b
- https://github.com/odaialdajani/floww-2/commit/8300af1645e124cf11918812985d4afa9f294d19
- https://github.com/odaialdajani/floww-2/commit/dbbd3d3c89ebeb4b5d0b4e75556315b5f36afa48
- https://github.com/odaialdajani/floww-2/commit/89074181796f0d6b3ff087877df3d1b1ee3176b2
- https://github.com/odaialdajani/floww-2/commit/78143ef867e5a858f64294b0ac0c0545ced89240

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #84 — feat(cmd-takeover): port verified backend work + wire C3 exposure

**Classification: owner-hold or unverified**

The principal C3 path is retained: GET public chain invokes annotate_contract_exposure, which calls canonical compute_raw_oi and multiplier resolver, withholding unknown/quarantined inputs rather than the old hardcoded-100 score. Route tests cover basis, adjusted contracts, explicit multiplier and missing gamma. This 32-file takeover also added pure wall/session/second-order domain modules and agentfield/QC changes; those are inventoried, not all independently executed or fully audited here. Do not imply entire takeover/owner acceptance from C3 wiring.

PR: https://github.com/odaialdajani/floww-2/pull/84
Historical head: https://github.com/odaialdajani/floww-2/commit/1524397e17c5a42c39bc2fb21b9802e3f4ee1bc9
Merge: https://github.com/odaialdajani/floww-2/commit/53d8237afa7c4410444e6fde76f1a76c19378ab7; ancestor of candidate: True.

API: files: 32 records / 1 pages, commits: 4 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [backend/routes/public_api.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/routes/public_api.py#L107) — `def get_public_chain|annotate_contract_exposure`; lines 107, 136, 137
- [backend/services/triad_projection.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/triad_projection.py#L21) — `def annotate_contract_exposure|resolve_multiplier|compute_raw_oi`; lines 21, 48, 51, 97, 105, 136, 151, 443
- [backend/domain/numeric_boundary.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/domain/numeric_boundary.py#L15) — `def coerce_scalar|bool`; lines 15, 17
- [backend/tests/routes/test_public_api_chain_routes.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/routes/test_public_api_chain_routes.py#L24) — `def test_public_chain_`; lines 24, 38, 43, 60, 76, 89, 100
- [backend/tests/services/test_triad_projection_backend.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/services/test_triad_projection_backend.py#L97) — `def test_`; lines 97, 102, 109, 117, 134, 147, 161, 167, 178, 193, 209, 215, 222, 227, 232, 245, 254, 259, 264, 275, 282, 297, 314, 334, 343, 348, 353, 361, 392, 405, 419, 429, 447, 453, 459

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/b1f06d1818d474c01561c6e55e4866ea50323a21
- https://github.com/odaialdajani/floww-2/commit/b662c18c00336271857b73885a65897e76e675bc
- https://github.com/odaialdajani/floww-2/commit/d8c71527f18fdce3095fd960c42be6de99167483
- https://github.com/odaialdajani/floww-2/commit/1524397e17c5a42c39bc2fb21b9802e3f4ee1bc9

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #85 — fix(eastern-clock): US DST rule for all four ET gates (rebased on #84)

**Classification: superseded/declined**

Fresh GitHub read confirms closed, not merged. Both discussion comments explicitly replace it with #86 after main advanced. Original ET patch is represented in #86/current eastern_clock and server/dispatcher callers; no missing merge or stale head should be recovered. Discussion URLs and all two comments retained in API evidence.

PR: https://github.com/odaialdajani/floww-2/pull/85
Historical head: https://github.com/odaialdajani/floww-2/commit/069fea9aca15c789343c473104d7a051034d4ec5
Closed unmerged; superseded.

API: files: 6 records / 1 pages, commits: 3 records / 1 pages, discussion: 2 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
Two fully read comments explicitly supersede this PR with #86.

### Current source and test evidence

- [backend/services/eastern_clock.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/eastern_clock.py#L55) — `def eastern_utc_offset_hours|def eastern_at_safe`; lines 55, 85, 131
- [backend/server.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/server.py#L467) — `def _eastern_now|eastern_now_safe`; lines 467, 474, 476
- [backend/services/alert_dispatcher.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/alert_dispatcher.py#L172) — `eastern_at`; lines 172, 176

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/da955aa1defcc008ef479add1b1a8268bccf2367
- https://github.com/odaialdajani/floww-2/commit/30c9dd1addb5e8b09d55e1ca3f0a2e0af73114e2
- https://github.com/odaialdajani/floww-2/commit/069fea9aca15c789343c473104d7a051034d4ec5

- https://github.com/odaialdajani/floww-2/pull/85#issuecomment-5882817235 — Superseded by the rebased branch. Main moved to 53d8237a (PR #84) while this PR was open, so its head no longer builds on current main. The rebased replacement carries the same three commits (ET gates, shared eastern_clock module, ledger finding) plus the H0 drift work. Closing rather than force-pushing, to keep this PRs history intact.
- https://github.com/odaialdajani/floww-2/pull/85#issuecomment-5882818204 — Closing in favour of #86, which is rebased on 53d8237a. Leaving this open with a stale head would make its green checks misleading.

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #86 — fix(eastern-clock): US DST rule for all four ET gates (rebased on #84)

**Classification: current intent retained**

Replacement #85 clocks are present. Server routes the live window, scheduler and SSE through _eastern_now (later upgraded to safe aware fallback); dispatcher calls shared eastern_at. Post-2007 DST arithmetic verified at both 2026 transition instants. The final 17-commit PR also fixes full-universe cursor truncation and absent/nonpositive multiplier handling; current prefilter returns full eligible list and project_window resolves multiplier canonically. Legacy eastern_at fallback still preserves UTC tzinfo; safe server path is explicitly distinct, so no blanket claim that every clock caller gained safe instant semantics.

PR: https://github.com/odaialdajani/floww-2/pull/86
Historical head: https://github.com/odaialdajani/floww-2/commit/613e7d3f35fdd2d68a711e4ef2937818767700ae
Merge: https://github.com/odaialdajani/floww-2/commit/605aca8a0c9dedaae3b9441ff008cc607eff2659; ancestor of candidate: True.

API: files: 11 records / 1 pages, commits: 17 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [backend/services/eastern_clock.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/eastern_clock.py#L55) — `def eastern_at|def eastern_at_safe|def eastern_utc_offset_hours`; lines 55, 66, 85, 131
- [backend/server.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/server.py#L467) — `def _eastern_now|et = _eastern_now`; lines 467, 482, 2791, 3179
- [backend/services/alert_dispatcher.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/alert_dispatcher.py#L172) — `eastern_at`; lines 172, 176
- [backend/services/universe_scan.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/services/universe_scan.py#L83) — `kept = ranked`; lines 83
- [backend/domain/wall_desk_snapshot.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/domain/wall_desk_snapshot.py#L40) — `resolve_multiplier|if mult is None`; lines 40, 163, 222, 223
- [backend/tests/test_universe_cursor_rotation.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/test_universe_cursor_rotation.py#L44) — `def test_`; lines 44, 60, 69, 79, 90
- [backend/tests/test_wall_desk_multiplier_missing.py](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/backend/tests/test_wall_desk_multiplier_missing.py#L52) — `def test_`; lines 52, 56, 64, 77, 88

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/caf2d7d4d98c6e4756e64740bf46d32f069232be
- https://github.com/odaialdajani/floww-2/commit/edf4c6ce95901023726452edc2e8767d6b60496c
- https://github.com/odaialdajani/floww-2/commit/0e5b437c14d77bf7fc56555ead3fc0fbd2322c5c
- https://github.com/odaialdajani/floww-2/commit/0b20de6b91abd123f9e2f7d6bfe24e111ec60231
- https://github.com/odaialdajani/floww-2/commit/57d985889fdb4ee42a39b7d41b0764aedd92f125
- https://github.com/odaialdajani/floww-2/commit/344725f426df0ed683a2253698c20c689b07dd30
- https://github.com/odaialdajani/floww-2/commit/31defe5fa7e2ce7cf08823db670b64f4155077b9
- https://github.com/odaialdajani/floww-2/commit/80399701228258cb60ac2c1a720f63d12fe4626e
- https://github.com/odaialdajani/floww-2/commit/4b571ef838576d61043ea1e94a6cf6ee49682a6e
- https://github.com/odaialdajani/floww-2/commit/030ac14b6c59a23c4809791b2b1e2ba3e6c638e2
- https://github.com/odaialdajani/floww-2/commit/ee3fc842c39a030ca190574e3dbd5c5bd36d8a53
- https://github.com/odaialdajani/floww-2/commit/e9ed3eb52840b66b72f83c9425441cdb57567b8d
- https://github.com/odaialdajani/floww-2/commit/0f47d03b07d72174b58a4d4c3eb0bfdc77518c3a
- https://github.com/odaialdajani/floww-2/commit/66009f04ace94641e89ba5a0dd63e1b19bf44165
- https://github.com/odaialdajani/floww-2/commit/36afe1ccc8ba4ff41f17c11206fcd5d9d157f6e7
- https://github.com/odaialdajani/floww-2/commit/14dbc1321fe3fd2048a5625a454399d449b0c991
- https://github.com/odaialdajani/floww-2/commit/613e7d3f35fdd2d68a711e4ef2937818767700ae

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

## #87 — feat(visual-finish): replay Play+scrubber, Triad position strip, S3 geometry proof

**Classification: current intent retained**

Recorded replay Play/scrubber, recorded range labels and compare-geometry tests survive. Later repair prevents duplicate slow playback requests with loading gating and only starts playing when stepOnce succeeds. Triad strip now rejects missing/non-numeric spot rather than Number(null)->0; it remains a current zone reference, not historical levels. Current test definitions cover slow playback, end-stop, scrubber and position; original screenshots are historical, not a fresh browser proof.

PR: https://github.com/odaialdajani/floww-2/pull/87
Historical head: https://github.com/odaialdajani/floww-2/commit/855cc55843e00e419fff47c93bb2dd3fbd0ea1c3
Merge: https://github.com/odaialdajani/floww-2/commit/b338c10d691065a0f42bf03e67c43205be7f23e0; ancestor of candidate: True.

API: files: 8 records / 1 pages, commits: 2 records / 1 pages, discussion: 0 records / 1 pages, review_comments: 0 records / 1 pages, reviews: 0 records / 1 pages. Counts reconciled: True.
No discussion comments, inline review comments, or reviews returned from fully paginated endpoints.

### Current source and test evidence

- [frontend/src/components/heatseeker/ReplayStrip.jsx](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/ReplayStrip.jsx#L208) — `!playing \|\| loading|if \(stepOnce\(\)\)|solstice-replay-scrub`; lines 208, 221, 269
- [frontend/src/components/heatseeker/ReplayStrip.test.jsx](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/ReplayStrip.test.jsx#L218) — `Play advances|slow recorded fetch|scrubber jumps`; lines 218, 237, 267
- [frontend/src/components/TrinityView.jsx](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/TrinityView.jsx#L483) — `const sp = typeof spot|triad-position`; lines 483, 512, 514, 515, 518, 522, 526
- [frontend/src/components/heatseeker/SkylitDashboard.test.jsx](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/heatseeker/SkylitDashboard.test.jsx#L1296) — `identical geometry inputs`; lines 1296
- [frontend/src/components/TrinityView.test.jsx](https://github.com/odaialdajani/floww-2/blob/6716946b109e43ced81bec6f2fec9c0c46332f14/frontend/src/components/TrinityView.test.jsx#L271) — `position strip`; lines 271

### Historical commits

- https://github.com/odaialdajani/floww-2/commit/f0477dd362af692af41734d8293d6d3cbc6e0015
- https://github.com/odaialdajani/floww-2/commit/855cc55843e00e419fff47c93bb2dd3fbd0ea1c3

**Depth/limits:** Static candidate source and historical patch/commit inspection; related tests read, not run as suites. No browser/runtime, durable user store, provider or owner acceptance proof.
Historical/current review is confined to the named substantive paths; full changed-file and commit inventories are in the JSON. No suite or owner acceptance is claimed.

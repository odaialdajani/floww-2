# Integration receipt — 2026-09-10

This supersedes the initial queue in CURRENT-TRUTH.md and the role prompts.
Always query GitHub and fetch main at boot; this file cannot attest future state.

## Reviewed candidates

| PR | Exact candidate | Local reproduction / repair |
|---|---|---|
| 57 | 11283188225668fa5ed76ab4e86f2755d2a609ba | 15 plumbing/summary tests; reject overflowing numeric inputs without dropping valid map entries. |
| 58 | 5c07acf5b85c6d542629818cb0805737152b5add | 58 intent/reconciliation/drift/paper-loop tests; 19 warnings. Durable pre-submission targets, exact order/asset/side/quantity checks, transactional journal updates, replay protection and explicit exceptions. |
| 61 | e65111b1abee90f9d174183e12aa2024bf8544d8 | 2 VEX scale-parity tests; intentional display scaling preserved. |
| 62 | d8af97bb481fe39ce0cc3d415de36709523c9fdf | 3 weight-parity tests; five-component description and actual confidence multiplier corrected without changing weights. |
| 63 | 306f1e604bdb52448a4b78f266bbca8c2532d4f9 | 8 registry tests; returned metadata isolated with deep copies; unproven pins downgraded to claims. |
| 64 | 40542b090e93bd1a8514bb14f8c01f33fabf07b0 | Full frontend: 66 suites / 536 tests. Proxy copy only; React act/open-handle warnings remain. No sweep-filter or responsive implementation claimed. |

All six exact heads had backend-tests, frontend-build and ruff SUCCESS when
queried on this integration pass; docker-build was SKIPPED, not passed.
These are root reproductions and source review, not a new independent Agent-4
verdict or a completed GSD contract pass.

PR57 merged normally as f949fa13e9c1bdaf0331cfaa0f204683dfa01b78.
The repository ruleset (22371460) requires up-to-date required ruff status even
though the separate branch-protection endpoint reported strict=false. The
ruleset is enforced. No bypass or weakening was used.

PR65 now serves as the combined integration candidate: current main plus the
exact PR58, 61, 62, 63 and 64 heads, merged in that order with normal Git merges.
There were no conflicts. This preserves every candidate's ancestry and tests
their combined tree once against current main. A successful local merge is NOT
a main merge; require CI at PR65's final head and GitHub merge confirmation.
After integration, fetch and assert every full candidate above is an ancestor
of origin/main. Check whether GitHub automatically closed the contained PRs;
never close an unabsorbed payload by assertion.

Combined product tree at 3210dd1e12d356b87ac1ec1e40249bf0ec8137b3 reproduced:

```sh
# cwd: recovery-harness-v5/backend; existing floww/backend/.venv interpreter
python3 -m pytest tests/routes/test_alert_plumbing.py tests/routes/test_alerts_summary.py tests/services/test_close_intents.py tests/routes/test_reconcile_close.py tests/routes/test_position_drift.py tests/services/test_discord_g3_paper_loop.py tests/services/test_vex_scale_parity.py tests/services/test_composite_weight_parity.py tests/services/test_calibration_registry.py -q -p no:cacheprovider --tb=short --show-capture=no
# 86 passed, 20 warnings, 144.30s; exit 0
# cwd: recovery-harness-v5/frontend; existing root frontend node_modules symlink
CI=true ./node_modules/.bin/craco test --watchAll=false --runInBand
# 66 suites / 536 tests passed, 24.97s; exit 0; React warnings retained
```

Ruff on all changed Python files passed. Subsequent local edits are documentation
only; final-head remote CI must still run before integration. Local environment
reuse is disclosed, not described as a fresh dependency installation.

## Preservation, not destructive cleanup

INVENTORY.json records the original 40 worktrees / 222 refs and seven dirty
worktrees. The integration worktree was added after that snapshot.
No old worktree, branch, dirty file, merge state or reflog was deleted/reset.
The two old detached merge attempts at /private/tmp/agent4-pr48-49-50 and
/private/tmp/pr50-merge-check stage seven backend files. Their staged versions
match origin/main at the original 2c33de0 baseline exactly (empty scoped diff).
They do not represent seven missing product changes. Their merge states remain
preserved in place; do not commit them as new integration work.

Other retained dirt: generated old yarn.lock; G3 kanban timestamp-only edit;
platform review task card; malformed v4 WAVE1-VERDICTS.md; literal zero-byte
...[truncated] in the control worktree. The latter is a real file, not display
truncation. Do not publish the false v4 merge claims or timestamps as current.
Non-ancestor archival branches are not automatically missing code: compare
patches and supersession before proposing any selective recovery.

## Boundaries

PR58's initial wrong-symbol reproduction in PR58-REWORK.md is historical RED
evidence, superseded by the repair above. Unmatched legacy orders are explicit
reconciliation exceptions, never invented fills. Actual broker reconciliation,
production migration/witness, deployment, data entitlement and empirical alpha
validation were not performed. Test data is synthetic; venue transport mocked.
No claim of comprehensive dead-code clearance or production readiness is made.

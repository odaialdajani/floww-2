# Independent critical-check refresh - 2026-09-27

PASS. The existing verifier freshly executed the exact 14 deterministic critical cases, comprising 17 test variants. All passed. The verifier's own before/after source check passed, and an independent post-run check matched all 885 current source-file identities to both the new initial record and receipt. No old source map was copied into the proof.

## Fresh execution

- Output: `output/research-critical-review-20260927-0036/`.
- Entry point: existing `backend/scripts/verify_research_comparison_critical.py`, via its module entry with `--output` pointing to the new directory.
- Interpreter: Python 3.11.15, 64-bit Windows. Launched in a hidden child using `CREATE_NO_WINDOW`; the verifier's controlled interruption children also use the hidden launch option.
- Receipt time: `2026-09-27T00:36:01.436143+00:00`.
- Result: 14 case statuses passed; 17 call-stage reports passed; pytest exit code 0. Log: 17 passed, 29 warnings in 9.21 seconds.
- Source inventory: 885 entries, unchanged before/after execution and again at independent receipt review.
- Synthetic fixture model entries: 3, matching the declared 3. Actual model calls: 0. Provider calls: 0. Frozen 32 functional comparison cases executed: 0.

## Exact identities

- New receipt `output/research-critical-review-20260927-0036/receipt.json` SHA256: `b93cfe5623b9e7af52afe8793fc7823f748c7ed8d212c21ba87f8e8649a9194e`.
- Proposal SHA256 recorded and independently rechecked: `305a42af3a8d86ed8e39ad314a99c592ad2fb57ccab53faf575e507e3aa71c2b`.
- Critical-test source SHA256: `769e2819ac970591b7b9126d98ef33fde081c581b4da8576364a46a71b3db93f`.

The initial source inventory, full per-case/per-stage reports, interpreter identity and test-source identity are preserved in the new output directory. The previous proof/report is unchanged. No source, proposal, raw input, grading or runner code was edited by this refresh.

## Scope

This is fresh deterministic critical evidence for the recorded current source inventory. It does not establish functional usefulness, actual browser paint, live model/provider behavior, paper readiness, database-crash recovery or production backup restoration. Controlled helper interruption and a local dispatch-uncertainty signal retain the verifier's explicit limits.

The receipt may be bound into current preparation after root review. Stronger-model and cost-acceptance questions remain pending; the daily cap and authorization boundaries are unchanged. This passing refresh grants no permission to run candidate models or the frozen functional comparison.

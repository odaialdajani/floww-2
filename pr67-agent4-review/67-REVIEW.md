---
status: review-complete
files_reviewed: 2
depth: standard
phase_dir: pr67-agent4-review
review_path: pr67-agent4-review/67-REVIEW.md
diff_base: 7dc7d5dc0a8c54a6ccdb2a622deb0a8a38ffe99b
critical: 0
warning: 0
info: 2
total: 2
timestamp: 2026-09-11T00:50:00Z
---

# Agent-4 Review: PR67 — fix(eval): gate walk-forward scoring on point-in-time-complete envelopes

## Scope

- **Head:** ceed598aa436ddcda79010bf2c31ea249cba7a7c
- **Base:** 7dc7d5dc0a8c54a6ccdb2a622deb0a8a38ffe99b (current main, PR58 merged)
- **Files:** 2 changed files, 121 insertions
  - `backend/services/eval_harness.py` (+27)
  - `backend/tests/services/test_eval_harness.py` (+94)
- **PR state:** OPEN, mergeState UNSTABLE (CI re-running after main merge)
- **CI:** ruff/SUCCESS, frontend-build/SUCCESS (rerun), backend-tests/IN_PROGRESS

## Summary

PR67 fixes an integration defect between PR59 (event_envelope) and PR60 (eval_harness): `costed_hit_rate` scored all rows including those with missing_event_time — no point-in-time gate existed. Adds `pit_filter()` and `costed_hit_rate_enveloped()` to filter before scoring. Rows with missing_event_time are excluded; unknown stays unknown.

## Findings

### INFO-1: Fix is correct and minimal (Info)

**File:** `backend/services/eval_harness.py:89-113`

The fix adds two functions:
1. `pit_filter(envelopes)` — filters to point-in-time-complete envelopes only, returns (predictions, actuals)
2. `costed_hit_rate_enveloped(envelopes, ...)` — calls pit_filter then costed_hit_rate

The defect is correctly documented: raw `costed_hit_rate` scores all rows including incomplete ones. The fix preserves the raw function for callers that don't have event_envelope data. Unknown stays unknown — no timestamp fabricated.

No action needed. The fix is minimal and correct.

### INFO-2: Tests properly reproduce RED before GREEN — but the defect test could be sharper (Info)

**File:** `backend/tests/services/test_eval_harness.py:96-190`

The test class `TestPointInTimeIntegration` has 4 tests:
1. `test_pit_filter_excludes_missing_event_time` — verifies filtering works
2. `test_costed_hit_rate_enveloped_filters_before_scoring` — verifies enveloped scoring gives correct result (1.0 for one correct call)
3. `test_costed_hit_rate_enveloped_empty_when_all_incomplete` — verifies empty result when all rows incomplete
4. `test_raw_costed_hit_rate_scores_all_rows_including_incomplete` — documents the defect: raw scores both rows (0.0)

The defect test (#4) explicitly asserts the raw function scores both rows — this is the RED reproduction. The enveloped tests verify the fix. Proper RED→GREEN pattern.

**Deeper finding — the defect test documents behavior but doesn't pin the boundary:**

Test #4 asserts `costed_hit_rate` returns 0.0 when given one correct and one incorrect prediction — this is the "both rows scored" defect. But it doesn't test the boundary: what happens when there are TWO complete rows and ONE incomplete? The raw function should score 2 rows (both complete) and the incomplete row should also be scored (defect), giving 3 total. The test only uses 2 rows total (1 complete + 1 incomplete), so it doesn't expose whether the defect scales with more rows.

Also, the test uses `pytest.approx(0.0)` for the defect assertion — this is correct but fragile. If someone "fixes" the raw function to also filter (which would be the wrong fix — it should remain unfiltered for backward compatibility), the test would still pass because 0.0 == 0.0. The test documents the defect but doesn't prevent a well-meaning but wrong fix.

**Recommendation:** No code change needed for merge. The tests are adequate for the fix. If a future card adds more evaluation tests, add a boundary test: 2 complete + 1 incomplete → raw scores 3 rows (defect confirmed at scale).

## Verdict

PR67 fixes a real integration defect between PR59 and PR60. The fix is minimal, correct, and properly tested. No blockers.

**Blocker:** None.
**Advisory:** None.
**Merge readiness:** CLEAR for merge after backend-tests CI passes.

## Limitations

- This is a code review, not a broker witness, visual owner signoff, or profitability proof.
- Green tests do not establish alpha or production readiness.
- The fix only addresses the eval_harness/event_envelope integration; no other modules reviewed.

## Next action

Wait for backend-tests CI to pass, then merge PR67. If backend-tests fails, diagnose and fix before merge.

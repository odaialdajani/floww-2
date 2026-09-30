# R12 published-base recovery

Baseline: `5312fe569f876be5ad05920218742424348234ce` (PR #88). Recovery branch:
`codex/opus-recovery-r12`. This is a bounded repair of the published code,
not a receipt for Opus's unavailable Mac checkout.

## Availability

At inspection, GitHub exposed 21 heads and no open PRs. None provided the
reported Opus checkpoint, `OPUS_STATE.md`, or its reported 23 unpushed
commits. The pasted reasoning is a task list, not an implementation diff.
Do not overwrite that local work or merge the old PlayWalls branch wholesale.
The next integration owner must first obtain its exact branch, base/head,
status, commits and uncommitted diff, then compare this repair by content.

## Repairs and production paths

- Triad's `activity` label claimed delta weighting while reading unweighted
  volume. `gexBases.js` now supplies shared display metadata, and the mounted
  Triad/GEX controls expose `session_delta_volume` separately. Formulas remain
  backend-owned; no extra upstream call is introduced.
- `wall_metric_breakdown` now supplies wall-local session volume times
  absolute delta, with separate usable/missing/invalid counts. The inspector
  consumes those fields, never the scope total. Zero with valid inputs remains
  measured zero; no usable population returns null for this new value.
- Window failures used `window_dadgex_reason` while the inspector read
  `window_daddex_reason`. The server synchronizes both names; the inspector
  prefers the canonical key and supports older recorded packets.
- The live window kernel now reuses canonical measurement, option-type,
  multiplier, absolute-delta and dollar-gamma helpers. Boolean Greeks, unknown
  option types, explicit null/zero/invalid multipliers and adjusted contracts
  cannot produce activity. The existing documented absent-standard-multiplier
  policy is unchanged; absence and an explicit null are different contracts.
  Boolean cumulative volume is invalid. Bad spot is explicitly unavailable.
- Strike clicks now respect the same armed-Trade and live/replay boundary as
  cell clicks. This opens review only; no broker path is added.
- Recorded replay waits for a pending fetch before scheduling another step.
  A slow response no longer launches a second same-record request.
- Expand already rendered without a callback on baseline. It still renders by
  default, safely disabled without a function; explicit `hideExpand` controls
  visibility. This is a control improvement, not an invented missing-button bug.

## Actual local validation

All commands ran in the isolated recovery checkout on Python 3.12.14 and its
isolated test environment, with locked frontend dependencies installed using
the repository's CI `--legacy-peer-deps` mode. No dependency manifest or lock
change is included. The runtime and installation are not a served Mac bundle.

```
CI=true npm test -- --watchAll=false --runInBand
Test Suites: 110 passed, 110 total
Tests:       958 passed, 958 total
exit 0 (Jest warned about delayed shutdown before exiting)

CI=true npm run build
Compiled successfully. exit 0

PYTHONPATH=backend <isolated-python> -m pytest --confcutdir=backend/tests/solstice \
  backend/tests/solstice/test_r12_recovery_kernel.py \
  backend/tests/solstice/test_r6_2_red.py \
  backend/tests/solstice/test_r4_p03_red.py \
  backend/tests/solstice/test_s2_window_surface.py \
  backend/tests/solstice/test_s1_s2_canonical_boundary.py \
  backend/tests/solstice/test_resweep_population_and_weights.py -q
72 passed

ruff check backend
All checks passed!

bash qc/audit/truth_audit.sh
226 passed, 0 failed

python qc/audit/check_silent_excepts.py
OK (340 files scanned)
```

The backend command is explicitly a pure-unit subset. `--confcutdir` excludes
the parent server/Motor fixtures; it does not establish route, lifespan, Mongo,
full-suite, coverage or provider integration acceptance. Normal CI must still
run those gates. No tests were skipped, marked xfail or disabled.

Red evidence: before these fixes, the added kernel suite had 18 failures and
3 passes; the seven mounted-consumer tests all failed. The strike-arm and
slow-replay tests also failed before their fixes. Two additional boolean-volume
cases were reproduced against the baseline function before passing the repair.
An intermediate inspector scope error introduced during this repair was caught
by existing tests and corrected before the full frontend run.

The 58 protected Tide/Flowseeker paths match their baseline SHA256 hashes.
App.js, frontend manifests/config, credentials, models, kanban and other
worktrees are untouched. No live orders, deployments, restarts, capture
activation, retraining or automatic merge occurred.

## Still open; do not mark the whole Opus plan complete

1. Reconcile the actual unpublished Opus source, including its toolbar/layout
   edits and local tests. Preserve unique changes and identify any overlap here.
2. Full input/cell coverage contract, canonical profile projection and verified
   expiry scope. Contract counts and visible cell counts are separate quantities.
3. Backend conditional wall reads tied to observed interaction and coverage;
   sign-only bounce/reject/squeeze/flush remains a hypothesis, not readiness.
4. One stable canvas toolbar, Matrix + Profile, bounded Calendar/Multi and real
   resize/performance/browser acceptance. GEX/VEX keep independent unit scales.
5. Exact listed-contract review and scope/staleness guards; Solstice-owned scan
   route without changing protected legacy Flowseeker state.
6. Existing Lodestar context v2/evidence support for adjusted/replay/Triad. Keep
   unsupported requests unavailable until the server resolves their exact facts.
7. Credential-present offline-guard reproduction at the actual adapter seam,
   integrated backend CI, served-bundle verification and human comprehension.

SPX entitlement, provider configuration, commissioned capture, real sessions
and empirical predictive validation are separate dependencies. This receipt
does not claim profitability or a gap-free audit of every repository line.

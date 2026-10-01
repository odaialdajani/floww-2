# HERMES_REVIEW — independent contract & acceptance review

- Candidate: `912ce46560dc3528fdb2b13fbbb97535471867ab` on `solstice/r11-opus`
  (base `origin/main` = `ca3dd8b5`). Reviewed pinned in `/tmp/floww2-head`
  (detached @ candidate). No production files edited by review.
- Scope: Spark queue items 1–6 against the reference
  (main ca3dd8b5, PR90 head 72cdd943, PR89 merged). Prior CI receipts were
  NOT carried: every gate below ran on the candidate.

## Contract verified (independent fixture, spot 200)

`backend/tests/solstice/test_hermes_acceptance.py` (6 tests, all pass in
the pinned worktree): separately derived u = 2000 with calls/puts, measured
zero OI vs unknown, boolean/nonfinite/out-of-range delta, explicit-invalid
multiplier, adjusted quarantine and partial cells. Proven through canonical
fns, both delta grid kernels, wall rows, the real builder, coverage and the
inspector path. During derivation I made five arithmetic/expectation errors
(sign of put cells, zero-OI grid gating, adjusted handling in canonical fns,
raw partial status); every one resolved IN FAVOR of the implementation. The
four-surface values and the missing/invalid split hold.

`frontend/src/components/heatseeker/HermesAcceptance.test.jsx` (4 tests):
coverage/partial/invalid maps, mounted grid δ?/δ! markers (never $0), wall
inspector δ-invalid row. All pass.

## Item-by-item

1. Missing vs invalid delta: PASS. Distinct buckets end to end
   (canonical `invalid_delta`, kernel `invalid_delta` + `cell_invalid_delta`,
   coverage, `daddex_invalid`, profile `invalid` map, grid/inspector UI).
   Values for valid members unchanged.
2. Scanner gate: PASS. `check_silent_excepts.py` clean (342 files) in the
   worktree; the `routes/solstice_scan.py` fallback now warns with the ticker
   (red test pins log + absent-not-zero). API docs check current (373 paths);
   `git diff --check` clean. Expand/generation-guards/replay-fetch/armed-live
   suites green (47 tests).
3. Indigo reference: PASS by browser evidence (below) + mounted-component
   audit (GEX/VEX/Charm tabs only; Raw/Δ/Vol×|Δ| inside GEX; one toolbar;
   concise rail; Lodestar on demand).
4. Compare Raw+Δ: PASS. Two-pane raw-left/adjustment-right over one
   snapshot with per-metric units/scales, shared wall/scope/selection/scroll;
   Multi-map honestly metric-paned (not multi-symbol); bounded loaded dates
   and replay-context restore proven by the user-local tests (green under the
   offline network guard: 40 passed). Scope/ticker changes keep generation
   guards (existing suites green).
5. Resize/scroll/Follow/keyboard: PASS by browser evidence (below). Keyboard
   hijack fix verified live (ArrowDown stays in matrix, ticker unchanged);
   follow-pause and paused-selection suites green.
6. Lodestar: PASS (retention). Adjusted/replay stay gated with explicit
   reasons, pinned backend (`display_facts` gaps) and UI (`admissionBlock`).
   No extension was warranted; nothing invented.

## Required gates (exact candidate)

- Backend: 6837 passed + 37 skipped (`-m "not flaky_env"`, transport modules
  excluded), plus 26/26 transport+critical on rerun (one timing flake first).
- Frontend: 119 suites / 1010 tests passed (includes 9 Hermes/Spark-new tests).
- ruff, silent-except gate, API-docs check, `git diff --check`: clean.
- Protected manifest paths: zero diff. No force pushes, protected edits,
  deploys, restarts, credentials, model or trading changes.

## Visual evidence

`docs/solstice/r11/evidence/browser-receipt.json`:
`passed_fixture_browser_checks`, 13 viewports (desktop/laptop/768/640/390 +
200% zoom + profile + multi + symbols + calendar + triad), 60 resize
iterations with zero drift at every width, 0 page errors, signed-profile
zero-axis geometry verified (21 bars). All 13 screenshots present.

## Observations (re-verified after O1/O2 fixes)

- O1 (FIXED): explicit-invalid multiplier now lands in its own `invalid_mult`
  bucket on all three grid kernels (delta, session-delta-volume, activity),
  folded into coverage `invalid` with a separate key. No longer lumped into
  `missing` or silently dropped. Canonical fns and wall rows already used
  generic `invalid` via shared multiplier provenance — unchanged.
- O2 (FIXED): wall-local session-delta-volume skips delta evaluation for
  zero-volume members with unknown/unusable delta (canonical/grid parity)
  while preserving measured zero (zero volume + usable delta stays usable,
  adds 0) and still counting `volume_usable` and running OI evaluation.
- O3: the Zed strip-back backup lives at `/tmp/zed-wip-backup/` (patch +
  untracked tarball); kanban/BOTTLENECK_ALERTS.md is rewritten by an external
  watchdog (left untouched, excluded from commits).

## Verdict: PASS

Exact head `912ce465`, all required gates green, browser acceptance present,
no unresolved blockers. Browser pixels are fixture-preview only (no live
market session); SPX entitlement, commissioning and participant study remain
external dependencies, unchanged by this candidate.

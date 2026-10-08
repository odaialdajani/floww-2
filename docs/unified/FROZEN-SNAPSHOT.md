# Frozen candidate snapshot — baseline + reviewed slices (2026-10-08, C17-sealed)

Baseline: `8194eca43a580121901516b291c1b2435da7ce2c`.
Composition root: `work/floww-unified` (branch `fix/floww-unified-20261007`;
C17-GROUP committed at `746ddd5c` under explicit human authorization —
"continue both work opencode and cline … finish merge commit everything").
Parent snapshot: `c07b571d` (pre-C17; sealed U-series below).

## Manifest (sha256 at freeze time)

Backend slices (Cline-authored, OpenCode-reviewed ACCEPT):
- b3aa6f4d… backend/routes/trinity.py (U12 typed refusals)
- fdde4f24… backend/server.py (U13 read-budget families + boundaries)
- 9b3f333d… backend/services/related_price_series.py (U11 torn-DB catch)
- eab4b6eb… backend/scripts/export_legacy_decisions.py (U10, +normalized_rows)

Parent frontend work (reviewed U02/U04/U05/U09):
- fcea8627… frontend/.storybook/preview.jsx
- 31f400f6… frontend/src/NeutralTheme.css (new)
- 4c99c0f8… RangeAnalyticsWorkspace.jsx / e4d50c9e… its test
- e4f794c0… RecordedPriceChart.jsx / 53ec418a… its test
- c0e1e8fa… SkylitDashboard.jsx / c471c797… its test
- 6ca72ff3… frontend/src/index.js (theme import last)
- 27b5ada2… rangeAnalytics.js / f899bac3… its test

Unified tests (11 files): e25dbc57 dashboard_read_budget (27),
954112d6 execution_boundary probes (5), 70cfaadf history_integrity (7),
9ae6fa2f history probes (5), bc15938a legacy_export (6),
2d7d8a42 related_admission probes (6), 8d467387 related_admission (11),
b8675522 saved_scanner_admission (9), f927dc9a saved_scanner probes (5),
daf105b6 storage_restart (5), 1dc5bfba trinity_provenance (4).
Plus 1ffb4817 frontend unified-tests/context-generation (7).

## C17 slice (2026-10-08; OpenCode takeover, authorized)

- cec527fb… backend/services/triad_projection.py (per-strike
  n_measured/n_total/partial; exposure_by_strike projection)
- e6557e77… backend/routes/public_api.py (read-only
  GET /api/public/chain/{ticker}/exposure-by-strike)
- 57fe5a14… backend/tests/unified/test_exposure_by_strike.py (6 tests)
- 7624686d… frontend/src/agent/chatNavigation.js (exact multi-word chart
  names win over single-key ticker binding)
- d7eb8e5d… frontend/src/unified-tests/context-generation.test.jsx
  (updated expectation — 26/26 with nav suite)

Lane receipts: OpenCode `7b4cf2a8` (mirror + docs), Cline `1a7ff033`
(reconcile into storage-recovery lane; unified+recovery suites 126
passed). C17 ledger record pending→closed (deferral history preserved in
C17/DEFERRAL.md). Cross-lane byte-identity verified for all 9 files
(host-opencode ↔ host-cline backend+frontend slices ↔ floww-unified).

## Gates run ON this composition (exit 0 throughout)

- Backend unified: 90/90 → after C17: 96/96 (unified/), and 150/150
  combined run (unified + triad_projection_backend + s5_identity +
  api_docs_freshness).
- Ruff (0.15.22 CI pin) on slices + unified tests: clean (2 findings in
  my probe file caught and fixed mid-gate: unused var + import order).
- Frontend full: 168 suites / 2022 tests, exit 0, zero failures; re-run
  post-C17 2020+2 pass, 2 known flake suites (RangeAnalyticsWorkspace,
  TrinityView.r11) pass isolated 44/44 — same flake pattern as pre-C17.
- Production build (`craco build`): compiled successfully (exit 0),
  re-run post-C17.
- API docs freshness: 8/8 (post-C17 re-run included in the 150).
- Truth/silent gates: 60/60.
- Browser battery on the served pre-slice composition: 11/11 + 6/6
  interaction (re-run needed after redeploy serving THIS snapshot).

## Not claimed

Hosted backend/frontend/Ruff/Docker on this exact composition until the
PR merge + CI runs return. Live-preview re-serve of this snapshot
(needs preview restart = human word; previews currently serve
`97e16bbe`-era code). Peer countersign on architect verdicts (needs a
second mind). No readiness/profitability claim follows.

# Frozen candidate snapshot — baseline + reviewed slices (2026-10-08)

Baseline: `8194eca43a580121901516b291c1b2435da7ce2c`.
Composition root: `work/floww-unified` (files only, uncommitted —
H-PUBLICATION: no commit/push/merge without human word).
Status lines (18 total): 14 modifications + 4 new paths, nothing else.

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

Cross-lane byte-identity verified for every composed file at freeze time.

## Gates run ON this composition (exit 0 throughout)

- Backend unified: 90/90.
- Ruff (0.15.22 CI pin) on slices + unified tests: clean (2 findings in
  my probe file caught and fixed mid-gate: unused var + import order).
- Frontend full: 168 suites / 2022 tests, exit 0, zero failures.
- Production build (`craco build`): compiled successfully.
- API docs freshness: 8/8.
- Truth/silent gates: 60/60.
- Browser battery on the served pre-slice composition: 11/11 + 6/6
  interaction (re-run needed after redeploy serving THIS snapshot).
- Bandit: unavailable in this interpreter — CI-only, stated.

## Not claimed

Hosted backend/frontend/Ruff/Docker on this exact composition (needs
publication = human word). Live-preview re-verification (needs preview
restart serving this snapshot = human word; previews currently serve
pre-slice code). Peer countersign on architect verdicts (needs a second
mind). No readiness/profitability claim follows.

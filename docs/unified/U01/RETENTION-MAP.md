# U01 — Baseline census and retention map

Owner: OpenCode. Reviewer: Cline. Status: work recorded, pending Cline review of this sealed dossier.

Baseline: `8194eca43a580121901516b291c1b2435da7ce2c`
("Restore critical stock tools and broaden screener browsing").
Authoritative read root: `work/floww-unified` (HEAD == baseline, verified).
Write lane for this dossier: `work/host-opencode` (HEAD == baseline, verified).

## 1. Census (recomputed, not borrowed)

- `git ls-tree -r 8194eca4 --name-only | wc -l` = **5167**.
- Sorted path-list SHA256 = `691a7d54542d02aededa085663b4f3fafe55303acf197d7a867d10989be88f9a`
  — matches `scope.json` inventory claim exactly.
- `frontend/src/components/flowseeker/` at baseline = **77 paths**
  — matches the protected friend set; `Frontend-Audit.md` records 77/77 equality.
- The `5168` figure from `git ls-files` in `work/floww-unified` is explained:
  staged-but-uncommitted candidate addition `frontend/src/NeutralTheme.css`
  (+1). It is a declared candidate addition, not baseline drift.

## 2. Preservation proof (candidate vs baseline)

- `git diff --name-only 8194eca4 -- frontend/src/components/flowseeker/` in
  `work/host-opencode` = **empty**. All 77 friend files byte-identical.
- `work/floww-unified`: same empty result. No friend edit in either lane.
- Route identity intact at candidate (`frontend/src/shell/navConfig.js`,
  unchanged): 8 NAV_ITEMS — Screener (`flowseeker-pro`), Stock chart
  (`heatseeker`), Market view (`trinity`), Options map (`skylit`),
  Extra studies (`steal-three`), Portfolio, Journal, Broker (`public`).
  Labels, route IDs, group order preserved. No alias added.

## 3. Dirty classification (candidate delta, all parent-owned)

Modified vs baseline (10 files, +27/−5) plus 2 additions:

| Path | Change | Owning review task |
|---|---|---|
| `frontend/.storybook/preview.jsx` | +3/−1 | U04 (theme import context) |
| `frontend/src/components/heatseeker/RangeAnalyticsWorkspace.jsx` | +2/−1 | U02 (null-date compat) |
| `frontend/src/components/heatseeker/RangeAnalyticsWorkspace.test.jsx` | +7 | U02 |
| `frontend/src/components/heatseeker/RecordedPriceChart.jsx` | +3/−1 | U05 (PNG neutral bg) |
| `frontend/src/components/heatseeker/RecordedPriceChart.test.jsx` | +3 | U05 |
| `frontend/src/components/heatseeker/SkylitDashboard.jsx` | +2/−1 | U09 (fragment-brace correction) |
| `frontend/src/components/heatseeker/SkylitDashboard.test.jsx` | +1 | U09 |
| `frontend/src/index.js` | +1 | coordinator-owned import (NeutralTheme last) |
| `frontend/src/lib/rangeAnalytics.js` | +2/−1 | U02 |
| `frontend/src/lib/rangeAnalytics.test.js` | +8 | U02 |
| `frontend/src/NeutralTheme.css` (new, untracked in this lane; staged in `work/floww-unified`) | theme overlay | U04 |
| `backend/tests/unified/test_dashboard_read_budget.py` (new, untracked, present only in `work/floww-unified`) | read-budget evidence | U13 (Cline-owned; not touched here) |

SHA256 of candidate source files: see `EVIDENCE.json`.
`NeutralTheme.css` SHA256 (identical both lanes):
`31f400f6e8834a6afae7996c61a75200280dfc96c7a987f59bca605929be008a`.

## 4. Retention decisions

- KEEP latest-build features: chart image export, related-stock comparisons,
  broader stock browsing, saved activity, both simultaneous Stock studies,
  scrolling price/options layout, current ticker/view-preserving navigation.
- KEEP all 77 friend files immutable; Tidehunter/ML artifacts, settings,
  package/build files, auth/order boundaries read-only.
- DO NOT restore old r11 labels/default map view: ten earlier manifest paths
  differ and newer friend files would be omitted. Latest labels stay.
- Older Triad desk proposal (`630716f5`) stays a separate unpromoted
  proposal: reviewed under U03 only, never copied into the app.
  (Note: an OpenCode T03 consumer repair `8320b0ab` was pushed to the
  proposal branch `solstice/opencode-r19-triad-desk-20261007` under the
  prior packet before this harness initialized; it does not touch the 8194
  candidate and awaits Cline review there.)
- Scope omissions: full line-by-line review of all 5167 paths is NOT claimed;
  classification is inventory + targeted source/behavior checks per task.
  Generated `frontend/build/` (floww-unified only) and `node_modules`
  symlink loops are excluded build artifacts, not source.

## 5. Next

Cline: review this dossier against the sealed snapshot. U01 acceptance =
review complete, not a source change.

# U18 prep — full frontend gate on the current candidate (NOT acceptance)

Date: 2026-10-08. Lane: `work/host-opencode` (baseline `8194eca4` + parent
work + U09 matrix; no source change between run and this record).

## Result

`CI=true npx craco test --watchAll=false` (frontend/):
**168 suites passed, 2022 tests passed, 0 failed, exit 0.**

A prior run the same day showed 5 failures across 3 suites; a clean
immediate re-run is fully green with no source change. Failed suites varied
between runs (timing-sensitive suites under parallel load). Classified as
flakes, not regressions: no failing assertion references parent-touched code
paths, and all parent-file suites (rangeAnalytics, RangeAnalyticsWorkspace,
RecordedPriceChart, SkylitDashboard, context-generation) are green in both
runs. Full log retained outside deliverables (temp scratch, not shipped).

## U17 prep (routes, same candidate)

Eight NAV_ITEMS verified in source (`navConfig.js`, unchanged): Screener,
Stock chart, Market view, Options map, Extra studies, Portfolio, Journal,
Broker. Route/shell suites green inside the full run. Real-browser
eight-route + responsive + keyboard evidence still requires the frozen
snapshot (U17 BLOCKED until U06–U08 accept).

## Standing

This is prep evidence only. U18 acceptance needs the frozen composed snapshot,
unchanged re-run, and Cline review. No commit, no publication.

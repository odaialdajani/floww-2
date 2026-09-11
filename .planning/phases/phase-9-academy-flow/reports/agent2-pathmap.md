# Agent 2 Pathmap — Tidehunter Pro Flowseeker Frontend

**Agent:** 2 / Muse Spark 1.3 · **Branch:** main · **Date:** 2026-09-03
**Lane:** Frontend only, fixture-first, no backend dependency

## Discovered Frontend Paths

### Flowseeker components (existing)
| File | Lines | Role |
|------|-------|------|
| `frontend/src/components/flowseeker/FlowseekerProBlademap.jsx` | 2137 | Monolith: Pulse tape + Scanner + alerts + conviction — **decompose target** |
| `frontend/src/components/flowseeker/FlowseekerProBlademap.css` | — | Scoped `.fsb-*` styles |
| `frontend/src/components/flowseeker/scanLogic.js` | 620 | **Single-source formatters** — fmtUSD/fmtK/fmtIV/fmtClock/fmtAge + business logic (mkScanRow, scanScoreOf, evalAlerts, tickerRollup, bizDTE, volSigma, oiChange, etc.) |
| `frontend/src/components/flowseeker/FlowseekerProBlademap.test.jsx` | 294 | Pulse helpers: mapPublicChainToRows, pulseScore10/Signal/Badges, aggregatePulse, pruneBuffer, pulseHedge |
| `frontend/src/components/flowseeker/BlademapActiveMount.test.jsx` | — | Mount/integration test |
| `frontend/src/components/flowseeker/scanLogic.test.js` | 843 | Full scanLogic coverage (estimateDelta, bizDTE, evalAlerts, streakOf, tickerRollup, archetypeOf, etc.) |
| `frontend/src/components/flowseeker/HISTORICALFEATURE.md` | — | Historical notes |

### Pulse / Scanner / Tracker / Chart (all inside the monolith today)
- Pulse tape: inline JSX in Blademap (~lines 700-1400), helpers pulseScore10/pulseSignal/pulseBadges/aggregatePulse/pruneBuffer at top of file
- Scanner: inline JSX + state (scan, scanAt, scanSort, scanMin*, scanDteF, scanQ, scanSideF, baselines, history)
- Tracker: not yet extracted — to be built in W3
- Chart modal: not yet extracted — to be built in W3
- Overview bar: not yet extracted — to be built in W1

### Fixture locations
- **Existing:** none dedicated — fixtures are inline in tests or fetched live via `/api/flowseeker/*`
- **New (this lane):** `frontend/src/components/flowseeker/fixtures/` — JSON fixtures for every wave, fixture-first per PLAN.md C1

### Test locations
- `frontend/src/components/flowseeker/*.test.jsx` and `*.test.js` — Jest via `craco test` (CRA)
- New tests co-located: `PulseTape.test.jsx`, `OverviewBar.test.jsx`, `TabConfig.test.js`, etc. alongside source

### Tab / Config persistence (existing)
| Key | Purpose |
|-----|---------|
| `fsb-scan-prefs-v1` (PREFS_KEY) | Scanner prefs: scanTypeF, scanMin*, scanSort, alertScore, alertRules, notify, advanced |
| `fsb-scan-alerts-v1` (ALERTS_KEY) | Alert tape (capped 100, pruned to today + yesterday) |
| `fsb-scan-alertseen-v1` (ALERTSEEN_KEY) | Dedup timestamps per rule key, 24h window |
| `fsb-scan-firstseen-v1` (FIRSTSEEN_KEY) | First-seen map per contract per session day |
| `LASTSEEN_KEY` | Away digest timestamp |
| `fsb.pollMs` | Poll interval |

New lane adds (W4):
- `fsb-tab-config-v1` — per-tab serialized config (filters, columns, highlighting, ticker scope, cap, sort, schemaVersion)
- `fsb-tracker-v1` — bookmarked tracker items, localStorage-first

### Formatter single source
- `scanLogic.js` is the single source: `fmtUSD`, `fmtK`, `fmtIV`, `fmtClock`, `fmtAge`, `bizDTE`, `estimateDelta`, `scanScoreOf`, `mkScanRow`, etc.
- New code MUST import from `./scanLogic` — no duplicate formatters

### Config / API
- `frontend/src/config/api.js` — exports `BACKEND_URL` (read-only)

## Forbidden (not touched)
- `frontend/src/App.js` — global routing shell
- `backend/` — all backend
- Global styles outside flowseeker lane
- Other product features (Wtipanel, RussellPanel, PublicPanel, Heatseeker)

If a forbidden file blocks wiring, a contract request is filed in `CONTRACT_REQUESTS.md` and the feature ships via fixtures/stubs.

## Agent 2 Target Structure (to be created)

```
frontend/src/components/flowseeker/
  FlowseekerProBlademap.jsx          # shell (decomposed, composes sub-surfaces)
  FlowseekerProBlademap.css          # extend with lane styles
  scanLogic.js                       # existing single source (untouched, imported)
  # W1
  pulse/
    spreadPosition.js                # spread_position formula + NO_QUOTE
    spreadPosition.test.js
    OverviewBar.jsx                  # NetPrem / P/C / FIR / session label / RVOL
    OverviewBar.test.jsx
    PulseTape.jsx                    # Fill + Side + spread bar columns
    PulseTape.test.jsx
  # W2
  context/
    earningsProximity.js
    sectorMap.js
    oiChangeColumn.js
    strategyBadge.js
    context.test.js
  # W3
  chart/
    ChartModal.jsx
    ChartModal.test.jsx
  tracker/
    Tracker.jsx
    Tracker.test.jsx
    trackerStore.js
  highlighting/
    highlighting.js
    highlighting.test.js
  tabs/
    tabConfig.js
    tabConfig.test.js
  # W4
  history/
    NetPremiumTrend.jsx
    StrikeDistribution.jsx
    VolOiFooter.jsx
    history.test.jsx
  feed/
    feedTabs.js
    tickerSearch.js
    resultsCap.js
    csvExport.js
    feed.test.js
  # W6
  filters/
    equityType.js
    filterState.js
    filterState.test.js
    FilterBar.jsx
    FilterBar.test.jsx
  # W7
  methodology/
    presets.js
    presets.test.js
    Checklist.jsx
    FunnelEmpty.jsx
    FunnelEmpty.test.jsx
  # Dark pool
  darkpool/
    DarkPoolPanel.jsx
    DarkPoolPanel.test.jsx
    levelsOverlay.js
  # Shared
  fixtures/
    pulseRows.json
    scannerRows.json
    overviewPayloads.json
    earningsCases.json
    highlightingCases.json
    darkPoolLevels.json
    trackerItems.json
    missingFieldStates.json
  types.js                           # JSDoc types
```

## Commit Plan
- This pathmap commit is standalone (no product files)
- Each wave commits only owned files, no force push, no rebase

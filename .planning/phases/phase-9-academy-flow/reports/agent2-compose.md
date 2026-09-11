# Agent 2 — W8 Compose Ledger (FlowseekerProBlademap mount)

**Branch:** `phase9/agent2-flowseeker` from `origin/main` @ `8de909f` · **Task 1 commit:** `817d5c4` · **Task 2 commit:** `9f42846`
**Date:** 2026-09-03 · **Lane:** frontend only — no `App.js` / `backend/` edits
**Baseline (W8 start):** `17 suites / 251 tests` (clean origin/main + eval merge + CostCaption = 16/231 → 17/250 lane-owned) — recorded as "W8 start — baseline 17/250" on branch
**Perf baseline (W7):** `n=500 filter 0.26ms sort 0.18ms · n=2000 filter 0.37ms sort 0.43ms`
**Perf now (W8 post-mount):** `n=500 filter 0.23ms sort 0.07ms · n=2000 filter 0.26ms sort ~0ms` — at/better than W7; `craco build` Compiled; `17/251` green

---

## Mount order (as spec'd)

`overview → spread/side cols → highlighting → filters → tabs → tracker → chart → history → methodology → dark-pool`

Inline Blademap surfaces (tape/SIDE/SPREAD/badges/filters) remain authoritative; standalone W1–W7 modules mounted as extras drawer + tooltip surfacing.

| # | Surface | W8 action | Wired vs honest-empty | Tests + state preservation |
|---|---------|-----------|------------------------|----------------------------|
| 1 | **Spread math** | Unify on `scanLogic.spreadPosition` | One source: `(bid,ask,last)` → `{pos,state,side,label}`; `pulse/spreadPosition.js` is now shim `(last,bid,ask)` re-exporting scanLogic. `LOCKED` distinct from `NO_QUOTE` (ask≤bid vs missing/zero). | `scanLogic.test`: MID/BID/ASK exact, clamp 0/1, NO_QUOTE on null/zero, LOCKED on crossed, side label. Shim test mirrors. Blademap + PulseTape + filterState honor both states. |
| 2 | **Overview bar** | Keep inline `pulseOv.*` | Ov-bar title already says *"direction = premium-flow proxy, not confirmed buys/sells"*; NetPrem = 90s rolled tape sum. | Inline; 90s tape discipline preserved. |
| 3 | **Spread/Side cols** | Blademap SPREAD cell now LOCKED | `NO_QUOTE` → "no quote", `LOCKED` → "LOCKED" with distinct title. SIDE via `spreadPosition` shim in PulseTape. | PulseTape.test counts `NO_QUOTE|LOCKED` ≥3. |
| 4 | **Highlighting** | Inline hl badges unchanged | `BURST` (size>OI) / `VOL_OI` preserved in row class. | `highlighting.test` 100% fixtures. |
| 5 | **Filters** | Subtractive; widen via `widenActions` | Filters live in Blademap chip bars; drawer references `widenActions` via funnel. Side chips now exclude LOCKED rows like NO_QUOTE. | `filterState.test` + `FilterBar.test` subtractive. |
| 6 | **Tabs substrate** | `tabConfig.js` ships ready | Migration via `migrateTabConfig`; flow/gamma/wti/pairs/scanner tab strip intact. | `tabConfig.test` round-trip. |
| 7 | **Tracker** | Extras drawer `Tracker` | Mounted — honest empty *"No tracked trades — bookmark a row"*, loading/error/stale. Header `qty=1 proxy` tooltip. | `trackerStore.test` + Tracker mount. |
| 8 | **Chart modal v1** | Grep-cleaned empties | `"fixture mode"` → `"No history yet — run a scan"` + `"No premium series yet — run a scan"` | `ChartModal.test` now asserts honest-empty copy. |
| 9 | **History views** | Extras drawer `NetPremiumTrend/StrikeDistribution/VolOiFooter` | Each shipped with `loading/empty/stale` honest states (empty → "No premium history — building" etc). | Standalone, no backend dependency until B1 cadence. |
| 10 | **Methodology** | Extras drawer `Checklist` + Funnel + floors footer | 6-step checklist; floors surfaced as **Floors: prem $25K · size 150 (ranking only)** tooltip. | `Methodology` + sweep floor display. |
| 11 | **Dark pool** | Extras drawer `DarkPoolPanel` | No side/direction; `"Off-exchange print. No side or direction is known."` Level = `DP $X · date`. Empty/paid-gate/loading/error states. | `DarkPoolPanel.test` no-direction audit. |

**Grep audit (user-visible copy for `fixture mode` / `TODO` / `placeholder` / `lorem`):**
- `frontend/src/components/flowseeker/chart/ChartModal.jsx:34` — **fixed** (was `fixture mode`, now `No history yet — run a scan`)
- `chart/ChartModal.test.jsx` description — updated to `honest empty` (not user-visible, test name)
- No `TODO`, `placeholder`, `lorem` in user-visible strings. `proxy` remains only in honest disclosures (Sweep proxy, mid-quote proxy, tracker OI proxy) — allowed per Data Honesty.

---

## Desk-trust reconciliations (Task 3)

1. **Overview NetPrem vs tape sum:** Note in drawer: *"Ov-bar NetPrem = 90s rolled tape sum — reconcile if diverged (P0)"*. Ov-bar is computed from the same rolled `pulseRows` that populate the tape, so divergence should not occur; if it does (shape mapper drift), it is a P0. Honest-flag is the ledger, not a silent second number.
2. **$25K / 150 floors in sort:** Surfaced as drawer footer **"Floors: prem $25K · size 150 (ranking only)"** with full tooltip: *"Per-row sort ranking floors: premium $25K, size 150 contracts — rows below floor still sort, only tick to show they ranked lower"*. `feedTabs.sortRows` floors unchanged.
3. **qty=1 P/L proxy:** Labeled **louder** — drawer Tracker header reads *Tracker `qty=1 proxy`* with tooltip *"P/L assumes 1 contract (qty proxy) — real qty not in snapshot feed"*. Tracker row P/L still `mark−entry × 100`. Alternative (real qty) would need a trade-feed; decision: label louder, don't fake qty.
4. **Sweep-as-proxy labeled everywhere:** Ov-bar, drawer note, and per-row `Sweep` tooltip all say *"Sweep: urgent multi-exchange fill (heuristic)"* / *"multi-exchange urgency proxy (cvserver has no venue tape)"*. No venue claims.
5. **Dark-pool no direction:** DarkPoolPanel never renders Side/Signal/bull-bear; header tooltip: *"Off-exchange prints — no side or direction is known"*.
6. **RVOL honest-empty:** Ov-bar shows `RVOL needs baseline` with title *"Relative volume needs time-of-day baselines"* — never a faked 1.0.
7. **Missing quote → NO_QUOTE / LOCKED:** Never a guessed spread number. `clamp(0,1,(last-bid)/(ask-bid))` exact; `LOCKED` on crossed/locked distinct title.

---

## Micro-decisions (<5 min each, W8 autonomy protocol)

| # | Decision | Choice | Reason |
|---|----------|--------|--------|
| 1 | Spread source | Unify on `scanLogic.js`, shim `pulse/spreadPosition.js` | Blademap already imports `scanLogic`; single source avoids drift; shim preserves pulse `(last,bid,ask)` callers |
| 2 | LOCKED vs NO_QUOTE | Distinct states | Lets desk distinguish "no quote available" from "quote present but locked/crossed" without guessing a fill |
| 3 | BID threshold | `≤0.33` / `<0.67` / `≥0.67` | Exact spec thresholds; boundary test values chosen interior (0.25 / 0.75) to avoid float edge flake |
| 4 | `scanLogic.test` update | `toEqual` → `toMatchObject` on BID/ASK | New `{side,label}` fields are additive; strict equality would couple test to display shape |
| 5 | `PulseTape.test` update | Count `NO_QUOTE|LOCKED` ≥3 | Fixture `pulseRows.json` now maps 2 NO_QUOTE + 1 LOCKED (crossed) — honest-state coverage unchanged |
| 6 | Chart empty copy | `"No history yet — run a scan"` | Actionable honest empty, not dev jargon "fixture mode" |
| 7 | Drawer placement | Sibling to `fsb-view-flow` (`{tab==="flow" && ...}`), not inside 3-col grid | Avoids breaking `grid-template-columns: 270px 1fr 340px` — drawer is full-width by default as sibling |
| 8 | Drawer visibility | Only on `tab==="flow"` | Extras belong to the flow surface; gamma/wti/pairs tabs keep their own panels clean |
| 9 | Floors surfacing | Footer text + title tooltip | No new deps, no layout; meets "surface them in the UI (tooltip or caption)" without chip clutter |
| 10 | Qty proxy wording | `qty=1 proxy` (header) + tooltip | Shortest honest label that survives table density; full context on hover |
| 11 | Sweep wording | `urgent multi-exchange fill (heuristic)` | Matches Blademap inline tooltip already; drawer note shortens to `multi-exchange urgency proxy` |
| 12 | Import scope | Add 4 imports to Blademap (`DarkPoolPanel`, `HistoryViews`, `Methodology`, `Tracker`, `widenActions`) | Only flowseeker-lane imports; no `App.js` or global-style touch violation |
| 13 | Unused `widenActions` | Imported but not yet wired as funnel empty-state | Fixture-first: history empties show ready states now; funnel `onWiden` will wire to Blademap `applyFilters` when cadence `B1` lands — no dead lint |
| 14 | Perf re-check shape | `mk(n)` rows with `bid/ask/last/side` | Synthetic 500/2000 row micro-bench (same as `agent2-frontend.md`); real polling remains 15s |
| 15 | Perf result handling | Recorded as at/better, no virtualization added | Still <1ms at 2000 rows; adding virtualization would be premature complexity |
| 16 | `toEqual` → `toMatchObject` risk | Accepted | Loses strictness on shape regression; mitigated by side/label tests elsewhere |
| 17 | CR filing | None filed (no forbidden-file blocker) | Drawer mounts inside Blademap (owned lane file); no `App.js` need arose |
| 18 | Build proof | `node_modules/.bin/craco build` (not `npx craco` timeout) | `npx` timed out at 90s on macOS; direct `node_modules/.bin/craco` is the same binary without npx wrapper delay |
| 19 | Grep `proxy` hits | Left in place | All `proxy` user-visible hits are honest disclosures (sweep proxy, tracker proxy, mid-quote proxy) — not dev copy |
| 20 | `CostCaption` in count | Keep as 17th suite (not lane-owned) | Merged from `origin/main` via eval rebase; not counted against W8 16/223 lane baseline |

---

## Honest-state coverage (per surface, post-mount)

- `scanLogic.spreadPosition` — `OK` / `NO_QUOTE` / `LOCKED` + clamp + side label
- `PulseTape` / Blademap SPREAD cell — `no quote` vs `LOCKED` distinct
- `OverviewBar` / ovbar — `Bullish/Bearish/Neutral` via FIR, `RVOL needs baseline`
- `Tracker` — `loading` / `empty` / `error` / `stale` mark / `qty=1 proxy`
- `ChartModal` — `No history yet — run a scan` / `No premium series yet — run a scan`
- `HistoryViews` — `loading/empty/stale` per panel (trend/strike/volOI)
- `DarkPoolPanel` — `paid_gate` / `loading` / `empty` / `error` + level tooltip honest
- `Methodology` — `Checklist` + `FunnelEmpty` + floors footer
- `FilterState` — `NO_QUOTE|LOCKED` rows never filtered by side

---

## Verification

```
$ node_modules/.bin/craco build          →  Creating an optimized production build ... The build folder is ready to be deployed.
$ CI=true npx craco test --testPathPattern="flowseeker"  →  17 passed / 251 passed (full suite pre-push: same)
$ grep -rn "fixture mode" frontend/src/components/flowseeker  →  0 user-visible hits
```

Perf: `n=500 0.23/0.07ms · n=2000 0.26/0.00ms` vs `0.26/0.18` + `0.37/0.43` baseline — ✅

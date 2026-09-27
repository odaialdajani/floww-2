# Desktop merge retention review

Reviewed 2026-09-11 22:34 UTC. Read-only source review against origin/main and integration merge 9d5e500a (parents 3b98ada0 and 7685a44b; common ancestor 1a512c33). Current reviewed delivery HEAD was 7213160b. No production source, provider, model, browser, order, or mobile action was performed. This is a bounded review of FlowseekerProBlademap, App/AppShell, SkylitDashboard and shared settings, not an audit of every incoming commit. Existing closed UI defects were not reopened.

## New actionable candidates

### 1. Shared settings can erase a just-saved Tidehunter layout

Severity: medium. Source-confirmed lost-update path; a mounted interaction regression should accompany the repair.

`frontend/src/components/SettingsPanel.jsx:29` captures the entire settings object during the parent render. Its refresh/default-ticker/accessibility handlers write that captured object back wholesale (lines 32, 37, 88), and `saveSettings` replaces the complete stored value (line 16). The same parent now embeds `TidehunterSettings` (line 100).

The child reads current storage and merges its own changes correctly, then dispatches `floww-settings-changed` (`TidehunterSettings.jsx:45-52`). Only the child subscribes to that event; the parent neither rereads at save time nor subscribes. A child state update does not rerender the parent. Thus the parent can subsequently restore the old nested Tidehunter object or omit it entirely.

Reproduction: open the desktop left-sidebar Settings panel; change its embedded Tidehunter layout mode or move a section; before any unrelated parent refresh, choose a general Refresh Rate or toggle general accessibility; reload. The Tidehunter change is replaced by the older parent snapshot. Start with no nested Tidehunter settings to observe the newly saved object disappear entirely. App passes the refresh/ticker callbacks at App.js:972, but they run after the destructive save.

Suggested repair: have general settings handlers merge only their changed top-level field into freshly read storage, preserving the current nested Tidehunter value. Ensure successful writes notify subscribers and update the general control state. Test the child-save then parent-save sequence. This is distinct from already closed Tidehunter-only persistence failure feedback.

### 2. Incoming measured Outcome Ledger has no retained desktop destination

Severity: medium. Confirmed missing incoming functionality; restore in the new Trust area without old page tabs.

At origin/main, FlowseekerProBlademap exposes an `Outcome Ledger - show calibration` button. Its `loadOutcomes` reads `/api/flowseeker/outcomes?days=60` and `/api/flowseeker/model`. The expanded table presents per-rule measured/censored counts, precision, matched-control rate/count, lift, confidence interval, MFE/MAE, and measured decay warnings; its heading also shows calibration model stage. These are real response fields, not demo controls.

Current FlowseekerProBlademap fetches `/alerts/quality` and `/journal/stats?days=90` (around lines 547-568), then renders conviction buckets and setup results (around lines 1944-1974). Those are different measures. No non-test frontend consumer remains for `control_rate`, `lift_ci`, `median_mfe_sigma`, `/outcomes?days=60`, or model-stage calibration. The backend routes remain (`backend/routes/flowseeker.py:2499` and `:2535`).

Reproduction: with a nonempty existing outcome response, origin/main's collapsed Outcome Ledger button opens the per-rule comparison. On the retained desktop, open Trust: the conviction/journal section exists, but there is no action or destination for the per-rule comparison or its decay warnings. A fixture-backed mounted check can prove this without provider reads.

The authoritative UI plan says to retain useful calibration in Trust and requires no lost reachable controls. It explicitly removes separate scanner/flow/gamma tabs, but does not direct deletion of these measured comparisons. Restore the fields with their original definitions, sample/censoring limits, unavailable states and warning semantics. Do not relabel the existing 30-day directional hit rate as the 60-day matched-control measure, or infer a trained model from insufficient samples.

## Retained or intentionally excluded

- AppShell's incoming provider integration is retained; the malformed incoming import was repaired.
- Incoming full ticker-universe search/cycling and Public page are retained in App. Source comparison shows no additional lost navigation destination in this bounded set.
- Skylit retains incoming zoom controls, measured row fit, expanded wider map and ticker traversal. Later changes add scoped readings and selected-map research rather than deleting these controls.
- The local v3 Board/Vector/Pulse/Lattice/Trust structure intentionally replaces old scanner/flow/gamma page tabs. Their absence alone is not a defect.
- Direct scanner broker submission is not proposed for restoration: the authoritative UI plan says planning must not submit orders, and the retained Plan action creates local journal drafts. Separate later paper/live gates still apply.
- Existing closed source-age, inactive baseline, interaction buffering, stable row identity, refresh timeout, persistence warning and malformed-reading fixes were not counted as new findings.

No full test/build/browser run was performed for this review. The two new findings should be validated with narrow regression tests before claiming repair.

## Authorized repair and bounded verification - 22:41 UTC

Parent authorized the two source repairs after this report. No other desktop redesign, mobile work, backend migration, provider/model call or order was performed.

- Settings regression first failed with saved mode `monitor` becoming undefined after a general refresh-rate save. General saves now merge only the changed fields into the latest stored object, notify same-window subscribers and subscribe to cross-window changes. Failed saves show an alert and do not invoke the applied-setting callback. Three mounted cases cover nested layout/screen preservation, external-window accessibility state and visible save failure; two existing nested-settings cases also pass.
- The missing Outcome Ledger destination first failed in the mounted desktop Trust section. Restored a separate OutcomeLedger component inside Trust while retaining current conviction/setup cards. It fetches nothing on initial render: the user explicitly loads historical outcomes and recalculates the local statistical estimate. All tests use mocked responses, never actual endpoints.
- Restored per-rule precision, matched comparison counts/rates, difference and confidence interval, measured/excluded counts, median best/worst moves, decline warnings, overall measured totals and calibration stage/sample/method status. Thin, malformed, empty and failed responses do not become zero or claimed accuracy. A failed reload clears previous figures. Missing time/coverage remain unknown. Fifteen-second deadlines end stuck requests; deactivation aborts requests, ignores late replies and does not recalculate on return without a click.
- Existing backend limitation is explicit: these legacy endpoints use yfinance daily history, and the model GET can fit a local statistical model. They are not current Public readings. No backend migration was attempted. The existing outcome hit definition counts absolute movement in either direction, with a 1% fallback when prior volatility is missing; the restored UI states that this measures movement size, not correct direction. It does not confuse this with the separate 30-day conviction hit rate or promise future trade performance.
- Final bounded run: four suites, **71 passed**. Command used `npm test -- --watch=false --runInBand --runTestsByPath` for SettingsPanel, TidehunterSettings, OutcomeLedger and FlowseekerProBlademap tests. The existing Blademap suite emits its previously recorded native/fake interval cleanup warning; no test failed. Whitespace diff check passed. Full combined frontend/build and real desktop rendering remain with the parent.

Changed source: SettingsPanel.jsx, new OutcomeLedger.jsx, and only the import/mount in FlowseekerProBlademap.jsx. Added focused SettingsPanel/OutcomeLedger tests. No commits made in this repair subtask.

## Source-policy refutation and repair - 22:48 UTC

An independent follow-up found that truthful legacy-source wording alone did not enforce `FLOWW_MARKET_DATA_PROVIDER=public`. The current chain/spot/scan paths forbid alternates in that mode, but the legacy outcome loader, model GET and refresh endpoint still called yfinance directly and could return a legacy cached report. Parent authorized a narrow guard repair rather than a provider migration.

The outcome loader now refuses before any memory/Mongo legacy cache read, ledger read or external fetch. Model and refresh refuse before history read, fit or write. A 503 explicitly says that compatible Public history is unavailable and no legacy recalculation is allowed. Missing, empty and whitespace-only configuration default to Public-only; explicitly configured legacy mode retains the existing behavior. No environment setting was changed. The UI shows the specific Public-only refusal and never presents an empty model as successfully fitted.

Strict mocked regressions first produced12 failures/2 passes. After repair and blank-value coverage,21 focused backend checks pass, covering the policy guards and existing calibration wire checks. A pre-existing model-computation test now explicitly selects legacy mode because that is the branch it exercises. All forbidden-fetch/fit mocks remain uncalled in restricted cases, including a seeded legacy cache. Ten focused frontend checks pass, including the specific refusal display. Ruff passes on the three affected backend files. No real endpoint/provider/model/order call was made. This supersedes the earlier suggestion that source labeling alone was sufficient for the restored control.

The same follow-up reviewed saved chart narration. Snapshot/expiry/strike binding, preserved substantive summary refusals and separate whole-chart flip were retained. Two reproduced parent-owned helper issues were reported for repair: a valid0.004 charm value rendered as+0, and a mismatched selected-cell unit could be relabeled from its contract suffix. This agent did not edit chartReading or AgentPanelAnswer; their repair/verification belongs to the parent.

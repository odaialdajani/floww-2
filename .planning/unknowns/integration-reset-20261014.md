# FLOWW integration reset — 14 October 2026

Status: **useful UI fixes implemented and checked; whole-product acceptance remains open.**
Latest continuation: [16 October completion evidence and executable gate](../eval/completion-20261016/STATUS.md), published review [PR #131](https://github.com/odaialdajani/floww-2/pull/131). This continuation supersedes old runtime/backing, unpublished-branch and blanket “no engineering remains” statements below; dated receipts remain historical. Engineering checks are not owner acceptance or complete historical-data recovery.
This supersedes the earlier chart-only “everything done/no gaps” claims, not the original packets or their evidence. The latest user priorities are the approved right inspector, Solstice/Triad usability, readable heatmap landmarks, chart context, Flow identity, historical-work recovery and performance. Deployment and trading are not implied.

## Current baseline and recovery

- Reviewed checkout: `/Users/nav/Documents/Codex/2026-10-07/so-we-have-a-really-big-3/work/floww-unified`.
- Fetched source/main: `4d911d3045809cab28ffe240855f77159c6bf7a2`, including PR130. New source edits in this pass are **uncommitted**; no push/main merge was performed.
- The requested repeating verification loop existed on a successor session at tick 79. Cleared it through Hermes's existing LoopManager and read back `cleared`; the original session was already cleared. Unrelated cron jobs and loops were preserved.
- Initial browser check found a “FLOWW — rebuilding” placeholder, no JavaScript assets and no running build. A real production build restored the application without restarting either service.
- Existing listeners: frontend Node PID10985 on :3000, backend PID10984 on :8002, both started 14 October 05:55. Frontend serves this checkout's build; backend cwd is this checkout's backend. Neither service was stopped/replaced. :8000/:8001 were not listening when checked.
- Proxy `/__floww_build` still carries an old hard-coded base; it is not source/load identity. Verified served assets directly instead. Current checked build after the continuation fixes: `main.ae0b2ec7.js`, `main.dd7974c8.css`.
- Runtime OpenAPI returned 393 paths and the owning heatmap, range, history and diagnostics routes. That census is not acceptance of all routes.

## What changed in this pass

### One right-hand review progression

Solstice and Triad use the same presentation component: **Wall → Contract → Flow → Public agent**. It wraps existing wall facts, exact-contract resolution, Ask Flow and grounded Public drafting. No second agent, context store or broker path was added.

Desktop selection review docks beside the map rather than covering it. The metrics rail returns when review closes; existing drawer behavior remains at smaller widths. Tabs have keyboard arrows/Home/End, selected state, unique tab/panel associations, one visible panel, preserved contract state and unchanged Escape/focus-return ownership. A changed owning selection resets the step; switching a step does not invoke research or repeat a contract read. Market observation and snapshot time are labelled separately.

Visible residual Lodestar headings/copy controls in the range canvas and Wall Desk now say Flow. Existing module names, saved-context keys, protocol IDs and historical evidence keep their old identifiers for compatibility. This is the same assistant, not another one.

### Read the heatmap without decoding every cell

A compact raw-OI landmark strip now shows:
- next structural zone below price, then the next one below that: **support watches**, not a promise;
- the zone containing the map's reference price;
- next structural zone above price, then the next above that: **resistance watches**, not a promise;
- call and put **concentrations**, selected from the existing measured side-specific strike values;
- source, loaded expiry count, quality, snapshot identity and separately qualified clocks.

Call/put and nearest-zone row labels are also on the strike rail. Raw landmarks stay distinct from adjusted/VEX cells. No new Greeks, dealer-position model, forecast or external feed was introduced. Unknown price, absent side, missing call/put values, invalid/duplicate rows, partial OI and non-OI/scalp basis are explicitly handled. Volume cannot be silently relabelled OI. One shared summary serves Triad's paired panes, avoiding duplicated panels that obscured the grid in the first browser pass.

Important distinction found during review: legacy `advanced_analytics.calc_gamma_flip_levels` calls the largest positive/negative **net** strikes “call_wall/put_wall”. That is not the same as largest observed call-side/put-side gamma. The new strip does not borrow those legacy names/values as side-specific observations. Its call/put labels explicitly mean loaded-scope concentration, not automatic resistance/support. The old backend calculation was not rewritten in this UI pass.

### Chart context without fake historical overlays

The chart has a separately labelled map-level reference beneath it. It is outside the candle plot and explicitly **not historical candle-time levels**. Missing recorded nodes remain gaps. The actual browser rendered 70 candles; a separate one-day provider-control GET returned 14 available frames. That does not prove saved historical options-node coverage: the earlier browser displayed 0/70 saved nodes. No present-day node was backfilled onto old candles to make that count look complete.

## Approved-preview parity and retained gaps

Reference: `/Users/nav/Documents/Codex/2026-10-02/he/outputs/Solstice-Triad-Preview.html`, its implementation contract, and the existing Tidehunter v3 plan. The preview is synthetic, not executable brokerage acceptance.

1. Navigation: all eight route IDs retained; no App.js/nav configuration changes. Screener/Tidehunter remains friend-owned and untouched.
2. Left controls: original view/Profile/mode/DTE/expiry controls retained. No removal of existing studies.
3. Matrix: same backend values, scope, signed palette, missing/zero/partial distinctions and selection contracts retained.
4. Right review: shared tabs and desktop docking implemented; actual owner visual approval remains NAV-VISUAL.
5. Triad: existing heatmap/volatility/Wall Desk remain distinct workspaces over their owning contracts, not deleted as duplicates. Next-listed and same-day are still separate.
6. Same-day failure: after-market 0DTE read returned no usable contracts. Next-listed returned 15 October with one owning expiry. The app must not silently switch the 0DTE request to that date.
7. Raw/adjusted: existing canonical surfaces retained; missing adjusted cells remain unavailable. No frontend gamma re-derivation.
8. Call/put and support/resistance readability: implemented as qualified concentrations and structural-zone watches. No predicted direction or calibrated probability claimed.
9. Replay: stored ownership and refusal behavior retained. Full production capture/restart/older-decision recovery remains separately open; do not infer it from list counts.
10. Chart: real candles, volume and existing estimated CVD retained; separately labelled map context added. Full candle-time node coverage is NOT proven.
11. Contract review: existing exact owning identity/preflight restrictions retained and tested. Opening a panel is not an executable quote or approval.
12. Flow: same provider/context/history path, no extra assistant. No paid product model turn or authenticated effective-settings campaign was run.
13. Public handoff: manual reviewed draft; copied ≠ delivered ≠ active. No native create/invoke endpoint or remote trace receipt invented.
14. Commissioning: policy/account/native/protection/activation decisions remain open. No broker order, cancel, connection, worker activation or new spending.
15. Tidehunter v3: historical plan/status inspected and live Screener sampled. Its source is protected; no new redesign or paid feed was activated. Automatic coverage unavailable/old readings remain visible, not described as fresh full-market coverage.
16. Accessibility: tab keyboard behavior, focus return and Escape checked. Desktop 1440 and 1280 checked; no new mobile optimization campaign or owner sign-off claimed.
17. Performance: latest warm browser map ready 1659ms, chart ready 2017ms; inspector tab actions 29–33ms. These are local single-run measurements, not an SLA. Build still warns about existing large bundles (1.37MB compressed lazy chunk, 372.19kB compressed main); broad code splitting remains future review.
18. Release evidence: local full frontend, targeted backend, build and real-browser checks below. Hosted/Docker/current whole-backend release acceptance was not run and is not borrowed from old SHAs.

## All branches, worktrees and original obligations retained

Machine-readable inventory: `../eval/integration-reset-20261014/inventory.json`.

- 82 local branches enumerated; 28 tips are not ancestors of origin/main. Patch equivalence further separates already-represented payloads from 133 non-equivalent commit instances across 16 branches. These counts are not 133 unique missing features: some branches overlap, and composition commits may already be represented semantically.
- 41 registered worktrees: 24 existing and 17 prunable registrations. No worktree, branch, reflog or dirty historical file was removed. No `prune`, reset, stash, rebase or blind cherry-pick was performed.
- Zero open PRs in the fresh `gh pr list` read; an empty PR queue does not mean all local work is integrated.
- The actual original ledger has **62 rows**, not the historical summary's 55. Every original row/field/acceptance/evidence/signature is retained verbatim in the inventory, with a separate current-review annotation. Original file and approved preview hashes are retained and checked.
- Historical ledger statuses are 54 ACCEPTED_AT_SHA, seven EXTERNAL_HOLD, one PENDING. They are NOT 54 new acceptances at this working tree.
- Original holds retained: NAV-ACCOUNT, NAV-CAPTURE, NAV-MODEL, NAV-NATIVE, NAV-VISUAL, NAV-RELEASE, NAV-PAPER-EXEMPT. Optional C17 remains original PENDING; current admitted projection/tests are evidence to review, not a manufactured owner countersign.
- Historical session discovery recovered the approved inspector direction, all-eight-route preservation, friend-owned Tidehunter restriction and the OpenCode/Hermes handoff. This is targeted session recovery, not a claim to have reread every historical message or attachment.

### Next branch-recovery order (preserve first)

1. `cmd/recovery-c0-20260928070352`: 20 patch-non-equivalent commits including pure exposure/session contracts and dead-wire repairs. Compare exact files and independent tests before admitting any payload; do not merge a 389-commit-old base wholesale.
2. `solstice/r11-opus`: three composition/chart commits including recorded TPO naked levels. Compare current implementations file-by-file; non-equivalent commit hashes do not imply absent code.
3. `work/floww-cline-unified-20261007` (two composition commits), `work/floww-opencode-unified-20261007` (one), and `solstice/opencode-r19-integration-20261004` (24): recover source/evidence/dossiers with explicit file ownership. Do not revive retired agent controllers.
4. Remaining non-equivalent branches: backup/audit-2026-09-pre-rebase (5), docs/model-audit-2026-09 (1), docs/status-refresh-2026-09 (1), docs/status-refresh-late (2), feat/h3-missing-input-neutrality (39), fix/audit-2026-09 (23), fix/health-endpoint-500 (4), fix/rerunfailures-missing (2), solstice/combined-r19-20261005 (1), solstice/opencode-r19-transport-regen-20261007 (1), verify83 (4). Each complete commit list is in inventory; source/evidence semantics remain unreviewed, not discarded.

## Checks actually run

- Full frontend: **199 suites / 2205 tests passed**, latest test-runner time 41.528s (56.517s command wall time), recorded in `gate.json`. Existing React act warnings and full-suite late-exit warning are disclosed; no passing test was skipped/weakened. Focused new/related five-suite run with `--detectOpenHandles`: **54 passed**, no handle warning in that output.
- New landmark tests: unknown/invalid values, partial OI, basis refusal, same-side exclusion, ranking, recorded identity, duplicate rows, paired-panel summary and actual grid wiring. New inspector tests: ordering, keyboard, mount preservation, context reset, no automatic ask and unique IDs. Failures were observed before the relevant fixes.
- Backend: **63 passed / 31 warnings**, current-checkout daily-checklist truth + Triad projection + price-history contract/horizons/sessions. Used the verified installed canonical venv because this checkout has no local venv; this is explicitly a shared-interpreter check, not a new environment/production certification.
- Production build: passed; final served main/CSS checked by the final gate. `make test`: 11 PASS / 0 FAIL. `git diff --check`: passed.
- Actual compiled browser: Solstice landmarks/70 candles/four tabs, map-versus-docked-inspector geometry, Escape and 1280 reopen; Triad actual next-listed map/four tabs/Escape. Zero page exceptions, blocked financial/model requests, or failed network responses in the final run. `browser.json` is the exact current receipt. An earlier run sampled chart state before load and saw zero candles; the harness now waits for real candles instead of treating that as success.
- Live read-only API: health200; one-day bars available; same-day unavailable with reason; next-listed usable with GREEK_TIME_UNKNOWN and executionEligible=false. Timings and exact scope in `api.json`. No exact quote-age/Greek-time completeness claim.
- Preservation gate checks 305 protected tracked files (including Tidehunter source, App.js/settings/model artifacts/test setup), the exact output allowlist, original ledger and preview digests, unchanged HEAD, no active copy of the requested loop, served/disk bundle identity and retained ledger count/fields.

## Continuation — chart integrity and broader recheck

The next source review found two additional real defects, reproduced by **17 failing regression cases before fixes**:

- Mixed-volume candles drew missing/invalid volume as a measured zero. Validating volume before all chart consumers now preserves gaps for missing, null, non-finite, negative, boolean and string values; real zero remains a measured zero. A mixed pane names its missing-candle count.
- The contract-premium pane stretched its entire response across the chart, ignoring candle times, replay and the panned window. It could reveal future option prices during replay, move unmatched bars to invented times, and bridge missing quotes. The pane now joins exact normalized instants, uses the same visible candle centres, splits gaps, refuses ambiguous local times and duplicate instants, and keeps its own dollar scale. Seconds/milliseconds and equivalent explicit timezone offsets match; genuine zero remains known. Alignment is memoized so pointer movement does not rebuild the whole lookup.

After fixes/refinement: **30 chart suites / 128 tests passed with --detectOpenHandles**, no late-exit warning in that targeted output. The complete frontend, expanded backend and build also passed as recorded above. Browser receipts are bound to the actual new bundle rather than accepted solely because an older receipt says passed.

`continuation-browser.cjs` / `continuation-browser.json` add:
- all eight real workspace **shell** reads, with their actual unavailable/loading messages retained; these are not full workflow or fresh-data acceptance;
- an explicitly synthetic, separate-browser-context compiled-chart check: mixed unknown volume stays a gap, sparse option closes do not bridge, and moving replay to the first candle removes the later $999 fixture price and its influence on scale. This is not a live option-price or trading-value claim;
- suppressed automatic theme-preference POSTs answered only inside that isolated review browser, avoiding edits to the user's saved preference. No research/broker mutation was attempted. Initial harness failures were a nested-main locator and an invalid assumption that record workspaces have the same selected sidebar button as market workspaces; changed to the actual owning main and breadcrumb, not production-source changes to satisfy the harness.

Fresh history evidence at receipt time: **70 price candles, zero matching saved nodes**, 2856 stored SPY snapshots in durable storage, first observation 7 October, latest 14 October 19:17:43 New York. Those stored rows are not 2856 matching candle-time observations and are not a complete recovery proof. Background capture reports disabled; recorder worker absent. This pass did not turn either on. A concurrent route-smoke read also honestly displayed price history unavailable while the dedicated behavior gate and a later direct control returned 70 candles. Cause of that intermittent unavailable response is **not established**; no corresponding recent bars-failure/429 log entry was found. Do not silently call it a permanent fix or hide it behind shell success.

A separate deterministic synthetic characterization confirmed legacy naming without changing any calculation: at fixed gamma, strike 90 has call/put OI 1200/1100, strike 100 call OI 900, strike 110 put OI 500. Both side concentrations are at 90; legacy positive/negative **net** extrema are at 100/110. The legacy strike-sign interpolation returns 106.43. This is source-convention evidence, not an estimate of actual dealer inventory or an approved gamma-method migration.

At this earlier 14 October checkpoint, no backend production source, protected configuration, model, broker path or service process had been changed. The 15 October continuation below records the subsequently approved backend reload and history-source changes. Bundle size, capture/recovery gaps and old branch acceptance stay open.

## Immediate unfinished work — do not mark complete

- P1: review the legacy call/put/net naming and gamma-flip methodology against canonical measured components without silently changing calculation conventions. Current presentation avoids conflating them.
- P1: complete time-aligned historical options-node capture/recovery proof. Expected/exported/missing/reopened records must be enumerated; price bars alone cannot recover missing nodes. The referenced older-decision recovery plan was not found at its prescribed path; recover its actual source rather than inventing its content. Preserve any original source service/store pending recovery and stop authorization.
- P1: do the branch-recovery queue above with per-file payload/semantic checks and the complete 62-row rebind ledger. Inventory is not acceptance.
- P1: owner review of the new production right inspector/heatmap readability; this work is not a complete cosmetic rewrite of Market view or the full old prototype.
- P1: independently admit any remaining Triad raw/adjusted/Wall Desk C17 gap against owning records and the exact envelope. Backend tests are not an owner signature.
- P2: resolve remaining React `act` and fake-timer warnings in tests without weakening their assertions. The full-suite async-handle warning was resolved in the 15 October continuation below.
- P2: broad bundle/startup optimization and all-eight-workspace end-to-end acceptance. No whole-app speed or no-dead-ends guarantee from this bounded check.
- Separate owner gates: effective product model settings/quality, native workflow review, account/policy/protection and release decisions. Trading stays uncommissioned; profitable execution is unproven.

## Re-run gate

From the repository root:

`python3 .planning/eval/integration-reset-20261014/verify.py`

Real-browser behavior (only existing read paths, no research/broker mutations):

`node .planning/eval/integration-reset-20261014/browser.cjs`

Full frontend: `cd frontend && CI=true npm test -- --watchAll=false --runInBand`.
These commands are bounded checks, not a recurring loop.

## 15 October continuation — approved review reload and test isolation

The user approved a controlled reload of only the review backend on :8002 and a test-only edit to the protected Screener cost-caption test. This candidate remains on `fix/floww-integration-reset-20261015` from baseline `4d911d30`. The original `floww-2` checkout, original recovery stores, other worktrees, and broker paths were not changed. The current source branches and the 62 original obligations remain inventoried; this continuation does not turn the inventory into acceptance.

- Identical overlapping Public.com history-bar reads now share one provider admission slot. Completed results are not cached as fresh reads. Budget refusal, provider unavailability, invalid bars, saved-scope mismatch, missing prior observation, aged observation and a recorded row without nodes have distinct diagnostics. The heatmap echoes the recorder's immutable scope selector separately from its request-cache key.
- The focused `CostCaption.test.jsx` run reproduced a real Axios request from `MarketCoverage` and a Jest open handle. That test now mocks the unrelated coverage and stock-directory children. The full suite exposed the same unintended request in `BlademapFlowView.test.jsx`; it now mocks only `MarketCoverage`. Both focused tests pass without an XHR error or open-handle report. Production Screener source stayed intact; the preservation gate scopes these two test-only exceptions and checks the other 303 protected hashes.
- The :8002 process was reloaded from this checkout with its prior environment and review database path. The new process served health 200 and the live history response contained `price_failure` and `node_coverage`. `FLOWW_ENABLE_LIVE_PUBLIC=0` and `FLOWW_SOLSTICE_CAPTURE=0` remained set; recorder health reported capture disabled and no worker.
- Current checks: frontend 200 suites/2210 tests passed both under `--detectOpenHandles` and, after the second Screener mock, in an ordinary full run that exited without an XHR or late-exit warning. React `act` and one fake-timer warning remain. Full backend 8160 passed/38 skipped with 71.42% coverage; focused backend 137 passed. Repository truth audit passed 226 claims, full backend Ruff and Bandit passed, production frontend build passed, and `make test` returned 11 PASS/0 FAIL. Docker was unavailable locally; hosted CI was not rerun for this candidate. The rebuilt Solstice/Triad browser check passed with no page or HTTP failures; the eight workspace shells and synthetic chart check passed. The saved-view browser showed 2/70 candle-time node matches and seven drawn saved lines; an independent bounded store-copy check found 31/70 candles with eligible nodes in at least one historical scope. Those are different scopes and do not imply complete capture.
- Speed evidence: the first compiled Solstice check rendered the grid in 5.2 seconds but waited 37.7 seconds for the chart. A timed repeat rendered the chart in 1.1 seconds, with its two history responses taking 483 ms and 375 ms. The latest rebuilt-bundle check rendered the grid in 632 ms and chart in 933 ms, with one observed history response in 364 ms. The cause of the first delay remains unproven. The build still warns about bundle size; no whole-product latency guarantee follows from these samples.
- Public.com remains the checked market-data path for the reviewed history and map reads. The configured Public API key and successful read do not prove all feeds, every workspace, live account behavior or order readiness. All visible **Ask Flow** entry points, chat headings, disclosures and accessibility labels now use the Flow name; internal Lodestar identifiers and stored protocol keys remain for compatibility.

The original branch reconciliation, older-decision recovery proof, complete historical node capture, hosted CI/Docker gates, owner visual acceptance, and separate model/account/native/release decisions remain open. The full local backend suite passed, but that does not close those gates. Keep trading and capture disabled and commissioning on HOLD.

## 16 October review-completion pass — committed and live

Committed as `6d411568` on `fix/floww-integration-reset-20261015` (local; not pushed). The review backend on :8002 was reloaded from this candidate with its preserved review database, capture off, worker absent, trading off, and `FLOWW_MARKET_DATA_PROVIDER=public`. The `PUBLIC_API_KEY` was sourced file→shell→process from the canonical checkout's `backend/.env` (value never printed/committed); the :3000 compiled-candidate proxy was restarted after its holder process was found dead. Three independent read-only audits (UI/spec, obligation/branch reconciliation, provider/history safety) were run against the exact committed candidate and are preserved in Hermes scratch `floww-review-20261016` (ui-audit.md, reconciliation.md/.json, provider-audit.md/.json). The reconciliation retained all 62 original obligations and all 82 inventoried branches with zero historical acceptances promoted; 16 branches still carry 131 unique non-equivalent commits requiring scoped review — inventory is not acceptance.

### Solstice/Triad review defects reproduced and repaired (RED→GREEN, focused suites pass)

- Unclassified cells were falsely reported as disappeared walls (`WALL_GONE`). `solsticeSelection.js` now distinguishes `NO_CLASSIFIED_WALL` from a genuinely gone identified wall, with an honest "still reviewable, no nearby substitute" panel.
- Exact-contract fields kept the previous cell's strike/expiry after selecting another cell in the same wall. Both desks now reset the resolver on a new selection while preserving user edits across tab switches (selection-revision keying).
- The right panel now keeps a persistent "Selected reading" context (stock, level, expiry, source, clocks) across all four Wall/Contract/Flow/Public tabs; heavy exposure detail moved behind an on-demand "Exposure details and coverage" disclosure; generic "reclaim and hold above zone" confirmation text replaced with honest not-supplied states unless the owning scenario exists (Triad drawer now passes its scenario).
- Both maps open centered on the actual price region with explicit "Center on price" / "Show selected level" controls; programmatic centering no longer pauses follow-spot. Triad Raw/Adjusted panes share strike axes and scroll together; the exposure profile centers on price and offers an explicit return-to-price control.
- Triad no longer paints today's wall zone across five days of historical closes: the price path is timestamp-anchored, missing/ambiguous closes break the line, and the current wall is labelled a current map reference, not historical candle-time levels.
- A model-free "Prepare fact-only brief" path was added to the Public handoff (grounded-AI path unchanged and still distinct); fact-only drafts stay local, cannot be saved as research reports, and refuse incomplete/conflicting selections.
- Expanded Solstice keeps the same review workflow available ("Review selected level" reopens the identical inspector state) instead of a separate fact-only destination.

Focused verification at this pass: `ReviewCompletion|SkylitDashboard|TrinityView|PublicHandoffReview` → **5 suites / 160 tests passed**. Full frontend: **202 suites / 2230 tests passed** (runInBand, no late-exit/XHR warning). Production build OK (`main.87743c9e.js`), bundle-size warning unchanged. Real-browser read-only review at 1440/1280/768/390: both desks pass (spot visible, synchronized axes, no page errors/HTTP failures/blocked writes, contract inputs reachable), receipt `.planning/eval/review-completion-20261016/browser.json` + screenshots.

### Public-only and history-safety repairs (subagent lanes, RED→GREEN)

- `backend/server.py`, `routes/flowseeker.py`, `routes/steal_three.py`: Public-only mode no longer falls through to CVServer on index/sparse misses, rejects warm non-Public cache reuse, skips Yahoo RV/IV producers (explicit `PUBLIC_ONLY_STUDY_UNAVAILABLE`, never invented zeros), and the drill chain fails closed with 503 instead of CV/Yahoo; legacy-mode behavior preserved and pinned by tests. New-record history identity now uses the full request scope key (maxStrikes included), so 80- and 200-strike builds no longer share one recorded selector. `tests/services/test_public_only_read_repairs.py`: RED 34 failed → GREEN **55 passed**; focused slice **104 passed**; Ruff clean.
- `routes/price_history.py`, `services/public_api_adapter.py`: shared history jobs have a 20s total deadline (admission + broker init + bars) with explicit `history_job_timeout` diagnostic; cold `_get_broker` cancellation during auth/account init now closes the discarded broker exactly once and propagates. `tests/services/test_history_resource_safety.py`: RED 10 failed → GREEN **12 passed** (repeated ×3); focused sweep **93 passed**.
- Combined focused backend slice at this pass: **137 passed** (public-only repairs + history safety + population-scope + admission/diagnostics/scope/echo + producer + spot-validation + live-app repairs). Full backend suite against the repaired candidate: **8228 passed / 38 skipped** (isolated DB, no coverage gate in this run; prior un-repaired full run 8160/38 at 71.4%). Ruff and Bandit clean on all changed files. One pre-existing budget stub (`test_public_advantage.py::test_public_chain_route_degrades`) needed an `acquire_n` method after the route moved admission into the adapter — stub extended, not the assertion weakened; that file now passes 48/48.

### Still open (unchanged holds)

- Live verification after the keyed reload: direct map read 79–80 strikes, spot ~761.9–762.5, `data_source=public_api`; days=1 history control returned 12 fresh Public candles with honest scope/gap diagnostics (`scope_not_available`, 12 `no_prior_observation` — real capture gaps, not zeros); full compiled-browser load reached **84 live measured cells with the spot chip visible in 7.8 s**, zero page errors. Earlier same-session reads showed transient `inflight_cap`/`provider_unavailable` refusals while slots were contended — the fail-closed behavior working, with recovery.
- Still open: full-suite React `act`/fake-timer warnings; bundle-size warning; the 37.7s first-load chart outlier remains unexplained; owner visual acceptance (NAV-VISUAL), hosted CI/Docker, complete historical node capture, older-decision recovery proof, branch payload reconciliation, account/model/native/release decisions. Trading and capture stay off; commissioning remains **HOLD**.

## 17 October continuation — merged integration, hermetic tests, durable review reload, PR publications

The chart/Flow and income repairs (`2b37c8fb`, `333e194a`, `181a76a4`, `67411248`) and the PR 1–131 audit package (`62e6aff1`) are merged into local `main` under `1d536839`. The audit package later received two gate-rework commits (`e0d8b1e1` lane/canonical baseline drift; `99c5d2a8` live kanban alert log tracked as a live record with its hash chain) after the gate proved `.serena/project.yml` had pinned the audit lane's checkout bytes and `kanban/BOTTLENECK_ALERTS.md` kept drifting under its live fleet writer; no protected or concurrent file was edited to make the gate pass, and `verify.py` passes at the current head with 131 rows / 5 fixed findings.

The canonical full-suite run then exposed 5 failed tests that the key-less worktree runs never saw: the host `backend/.env` (ADR-0002 public-only + a real `PUBLIC_API_KEY`) leaked into tests written against the legacy contract, so the merged Public-only policy refused legacy studies with 503 or skipped the directed cvserver failover. With `.env` neutralized all 5 passed; the repaired modules are the three provider-mode-scoped suites (`test_realized_vol_route`, `test_public_advantage`, `test_sparse_chain`) plus one autouse hermetic default in `tests/conftest.py` (host policy variables deleted at per-test setup; dedicated policy tests set them explicitly and still override). Backend full run at the pinned tree: **8,478 passed / 38 skipped, zero failures and zero offline-guardian errors** (the 8-record offline-guardian exception group from the same-period un-pinned tree is gone); frontend full 210 suites / 2,335 tests and production build green; Ruff clean; the pre-existing cross-module-order sensitivity of the agent-critical suite (only in hand-made orders that run a root consumer module before it) reproduces without the fix and fails worse at the pristine tree, so it is not introduced here.

The review backend on :8002 — the wedged 11:05 `server:app` process that no longer listened — was replaced by a reload from merged main with the preserved launch identity (`FLOWW_MARKET_DATA_PROVIDER=public`, capture/sweep/live/worker all 0). The first replacement was memory-backed by mistake; it was restarted after the original durable store was located and confirmed as the old process's live write target (`review-data.duckdb` in the long-running session work dir, 6,159 heatmap snapshots, last write 02:19:30Z). The final reload is durable-file-backed at that store with the lineage intact (latest observation preserved), capture worker absent, background capture disabled, and health green; data reads return available statuses with honest zero recorded-node counts for fresh scopes, which is the capture-off state, not fabricated fills.

On the remote: PR #132 (PR 1–131 audit package) merged to origin/main as `2b073563` with backend/ruff/frontend-build/docker checks green. PR #133 (chart-finish lane, head `333e194a`) was failing only its API-docs freshness gate, caused by the lane's regenerated `docs/api/openapi.json` being left uncommitted; committed as `bd1d4cbe` to the branch and its hosted checks were re-running at this note's time (ruff/frontend-build already green on the new head). The merge completed later that hour (`4fc6e85a`, all four hosted checks green), after which the one remaining publication left over from earlier lanes — the local-only stack (`67411248`, both audit-gate reworks, the hermetic test pin, this ledger) — was published through PR #134 (`integration/local-stack-20261018`): a direct push to `main` was correctly declined by the protected-branch hook, the PR ran all four hosted checks green, and it merged as `20d91860`, so local `main` and `origin/main` now point at the exact same commit and no commit of this program is local-only any more.

Still unchanged: all owner and recovery holds above (NAV-VISUAL, host-model/account/native/release, historical-node recovery, older-decision export), commissioning HOLD, and the protected Screener/Wheel files untouched.

### Later 17/18 October — act-warning sweep (standing P2 closed to 5), branch-review actionable closed

The standing full-suite React `act`-warning item was swept with a measured catalog first: eight suites produced 117 `not wrapped in act` console errors (`BlademapActiveMount` 34, `visual` 33, `SkylitDashboard` 24, `BlademapFlowView` 12, `OptionsChainTable` 8, `AlertsPanel.mlFailure` 3, `TriadDesk` 2, `FlowseekerProBlademap.X4` 1), all from fetch/prediction continuations resolving after each test's own awaits. The fix settles those chains inside `act()` at the emitting flows — per-test drains in six suites, act-wrapped collapse clicks replacing raw `el.click()` calls that fed remote loaders, and an afterEach drain in `SkylitDashboard` — with no assertion weakened, skipped, or reordered. Full suite at the fixed tree: **210 suites / 2,335 tests passing, warnings 117 → 5** (the residual five sit under two sessionStorage remount flows in `SkylitDashboard`; anchor drain attempts between the flows' own act windows did not reduce them further and the probes were reverted), and run time improved 61.3 s → 47.4 s. Tests-only commit `a562a55a`, open as PR #135; product code untouched. The fake-timer warning class showed no occurrences in the catalog (no fake timers in the suites at all).

PR #135 (`5813dcf6`, four hosted checks green) and PR #134 both merged; origin `main` and local `main` sit on one line with no divergence (`865a9114` after PR #136). The remaining engineering-executable item from the PR 1–131 branch review's six `missing-actionable` rows — `8300af16`'s `update_prometheus` age-gauge loop defect — was verified already repaired in the canonical tree (per-provider set inside the loop, `None` → `+Inf`); its demanded regression coverage was absent and is now added on PR #136 (three tests: both providers' age gauges emitted, never-succeeded provider emits `+Inf`, empty-monitor update is a no-op; file 29 passed, neighbor suite 44 passed, merged as `865a9114`). The false successor docs about shipped OI/DUO/DVO surfaces were already corrected by the 16 October completion lane; the OI/DUO/DVO surface implementation itself and the eight-surface registry tabs stay routed through their owner lane (explicitly not a wholesale old-branch restoration per the review).

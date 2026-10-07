# Critical desktop tool diff audit - 2026-10-07

Status: source retention reviewed; the final compiled five-page smoke check remains owned by the main task. Activation evidence is recorded by the main task; this reviewer does not independently claim the active build or complete app smoke result.

## Evidence compared

Before compaction: 3a081ad6, the actual preserved checkpoint (not 3a071). Current committed base: bdb6a8d8976a2a8763cb772cae64d481c436ed09. The working tree also contains concurrent Stock/search, dated Screener, Related side-column, and navigation-context repairs. Other work was preserved.

The commit diff spans 105 files. This audit focuses on critical desktop tool retention, rather than every changed calculation, order path, or record migration. Original source was read with git show. Current source inspected: App, HeatseekerDashboard, StealThreePreview, SkylitDashboard, FlowseekerProBlademap, TrinityView, StockDirectory, DataAccountMenu, Sidebar, AppShell, navConfig, and the study/context tests. Existing main-sync verification and earlier tab-audit notes were also read. Their historical test counts are not reused as current results.

## Retention comparison

| Area | Original critical content | Current location | Finding |
| --- | --- | --- | --- |
| Options map | 28 analytical dashboard children | Eight Study families below | All retained in source |
| Options surrounding studies | 25 components in the former App side column | Matching extraStudies family below | All retained in source |
| Extra | WheelIncomeScreenerPanel, DualGEXBadge, IVMidBadge | Options income, Exposure comparison, Volatility comparison | All retained |
| Market | TrinityView and TrinityVolatility | GEX Heatmap and Volatility buttons | Both branches retained |
| Screener | ConditionRows, ContractReview, DealerDrilldown, MarketCoverage, OutcomeLedger, ScreenBuilder, StockDirectory, TickerPicker, TidehunterSettings | FlowseekerProBlademap controls | No original source component deleted; full-directory trigger access was separately repaired |
| Stock | Original grid, metrics, cell/wall/contract review, replay, range, scenarios and comparison children | SkylitDashboard; source sidebar restored by its owner | No analytical child removed |
| Stock choice | SkylitTickerBar picker | Shared header TickerSearch/TickerPicker | Relocated; cold-directory failure repaired in source by main task |
| Full stock browsing | StockDirectory formerly also on Stock | Global picker dropdown: Full stock directory | Previously retained source was unreachable under controlled Screener selection; restored through one global entry point |
| Source/account | Header source, email/tier and sign-out | DataAccountMenu; email/tier also retained in Sidebar | Source and account action retained |
| Chat | Composer, saved date, saved answers, settings, expand/close, width controls | Shared assistant | Retained; selected-stock gap repaired below |
| Paused pages | Portfolio, Journal, Broker | Existing routes; duplicate embedded Broker replaced by Open broker records | Retained; trading not activated or exercised |

## Exact Options mapping

Each original analytical child is listed once. Former App studies are separate: merely keeping a component name elsewhere would not prove it remains reachable on Options map.

| Study | Original dashboard children | Former App side-column studies |
| --- | --- | --- |
| Price levels | FlipZonesPanel; NodeLifecyclePanel; AirPocketsPanel; NodeConfluencePanel | DashboardSummary; ScenarioPanel; GreekReferencePanel |
| Patterns | BeachBallIndicator; ReverseRugIndicator; RainbowRoadIndicator | OpportunitiesPanel; MarketRegimePanel; PressureCloudPanel |
| Options income | DualGEXBadge; IVMidBadge; WheelIncomeScreenerPanel | PositionSizing; TradeEntry; LivePolicyPanel |
| Changes over time | ConfluenceVelocityRow; VelocityModeBadge; TrinityConfluenceMeter; MaxPainBadge; MaxPainPerExpiryDriftTile | MlDashboard; MultiTimeframeGEXPanel; TradeAnalytics |
| Expected moves | StrikeConeBadge; OpportunityBadge; NewsBadge; RndDensityPanel | ImpliedMovePanel; VolAnalyticsPanel; ImpliedPDFPanel |
| More levels | RollingFloorsCeilingsPanel; TugOfWarZonesPanel; NodeClassificationPanel; StackedNodesPanel | RiskDashboardPanel; HedgeImpulsePanel; CharmIntegralPanel |
| Option exposure | VannaChart; CharmChart; CharmDecayPanel | UOAPanel; FlowTicker; VelocityGauge; ToxicityGauge |
| Market brief | BriefingStrip; GammaRegimeBanner | MorningBriefing; AlertsPanel; UsagePanel |

StudyFamily mounts a family on its first visit and then keeps it mounted while hidden. Tests change studies and return to an edited control, establishing state retention rather than only source-name presence. LazyRow retains first-loading behavior for the previously lazy children. Choosing an income family does not grant order authorization.

## Exactly what was removed or relocated

SectionHeader was a decorative title/stripe wrapper, with seven original rendered title calls. It was not unused in the original. It had no input, button, reading, request, state or trading action. Its title wrappers were replaced by the selector; every analytical child remains above. StatPill was declared but never rendered; autoDecimate/useCallback were unused imports in that dashboard.

Pulsing decoration, unconditional Live, ranks/development commands and unsupported journal-validated edge wording were removed. The summary now distinguishes No reading, Reading shown and Earlier reading.

Extra's quick picks and unverified free-text stock box were consolidated into the shared picker. Standalone Extra keeps TickerPicker. The original widthIV state was fixed at six with no changing control; IVMidBadge still receives width six.

The Options side column no longer stacks 25 panels at once; all 25 are in their matching families. No removed analytical study function was found in this scoped comparison. Full stock-directory access was a real lost interaction: the Stock mount was removed and controlled Screener hid its remaining trigger. That is corrected below; component-name retention alone did not prove access.

## Reproduced defects and navigation repair

A read-only browser probe found that failing both ticker-list reads hid the only picker under the tickers-dependent header condition. Its settled screenshot is C:/Users/DARK HERO/AppData/Local/Temp/floww-market-directory-total-failure-settled.png. Interceptions were removed after the probe. The main task owns the unconditional header repair and final compiled failure-state proof.

The same pass showed Selected SPY in the Extra header while Chat said Choose a stock. Actual shared-context-hook regressions reproduced Options unknown/null and Extra NVDA retaining an old SPY recorded context before the correction.

Navigation source is frozen in five files:

- frontend/src/agent/NavigationScreenContext.jsx
- frontend/src/components/heatseeker/HeatseekerDashboard.jsx
- frontend/src/components/heatseeker/HeatseekerDashboard.test.jsx
- frontend/src/components/heatseeker/StealThreePreview.jsx
- frontend/src/components/heatseeker/StealThreePreview.test.jsx

The first-sibling helper publishes page, chosen ticker and study metadata under the existing version-one contract. It invents no quote, observation clock, expiry or snapshot identity. It does not weaken version-two validation. The actual backend request_spec accepted both minimal Options SPY and Extra NVDA examples.

A valid same-page/ticker rich child remains authoritative for its complete selected record. The helper yields wholly: that record's reading, study, clock and identifiers remain unchanged when the parent changes its visible Study choice. These are distinct selections in that case; no merged rich-display semantics are claimed. The regression checks entire-record equality. Unmount only clears the helper's current ownership and cannot erase a later owner.

Fresh peer review found no blocker for present Options/Extra children. It recorded a future limit: a hypothetical rich child that publishes null without changing parent page/ticker/study leaves context empty until those props change. Today's Options/Extra children do not perform that publication/deactivation. The main task explicitly retained the yield-wholly contract without expanding scope.

## Full directory access repair

The global dropdown now exposes Full stock directory. StockDirectory is controlled and remains mounted outside the quick popup, so closing that popup does not destroy the modal. Selecting a validated provider row updates the shared stock and closes the modal. Focus returns to the stable Browse stock list button; it does not reopen the search popup. Existing uncontrolled StockDirectory callers still function. No duplicate chart picker/button was restored. Category, favorites, provider checks and paging remain in the shared picker. The modal retains search, Options enabled, full counts, paging and retry, adds its own list date or List time unknown, and keeps unavailable counts unknown without claiming No matching stocks from an incomplete list.

Four additional owned files: StockDirectory.jsx/tests and TickerPicker.jsx/tests. Backups preceded edits. Four new regressions failed before the fix; final two owned suites passed 34 tests. Six picker/caller/universe suites passed 67 tests, with the same 34 included; these counts are not added together. Fresh directory peer cleared selection/cancel/focus behavior and found two small response defects: impossible dates could roll forward and malformed paging flags could hide later pages. Calendar-valid zoned nonfuture date admission and consistent boolean paging metadata now have six added regression cases, all passed. Final owned Directory/Picker total is 40 tests (the earlier 34 remains dated evidence). Final independent directory peer confirmed the impossible-date probe now reports unknown and independently passed all 40 Directory/Picker tests; no remaining concrete close/selection/focus blocker. Native dialog trapping and the current compiled browser remain main-task checks. Receipts are full-directory-red.txt, full-directory-green.txt and full-directory-consumer-checks.txt in the navigation-context temp folder.

## Default Stock chart asking contract

A later independent check found that default price focus sent version-two map context with null snapshot/query/version and no expiry population. The actual backend rejected it before research. Only SkylitDashboard publication and its tests changed: price focus now publishes version-one navigation metadata (page, ticker, Price chart, navigationOnly), with no claim that loaded historical candles or a map snapshot were supplied. The existing selected-map version-two branch remains unchanged. A new regression confirms the complete selected-map record is identical after visiting Price chart and returning to Options desk. Two regressions failed before correction; the final Stock suite passed 115 tests. Both actual rendered contexts were exported as synthetic test evidence and accepted unchanged by the real backend request_spec (version one navigation and version two map). No model/provider call was made by that acceptance probe. Receipts: stock-chat-context-red-tests.txt, stock-chat-context-green-tests.txt, stock-chat-context-backend-acceptance.txt. The final independent narrow peer confirmed price/options focus ownership selects the minimal/full contract correctly, without inappropriate downgrade or later-owner clearing. The main task rebuilt and applied its checked version after the final source change; actual activation and complete app results belong to the main task, not this source review. A later whole-frontend run exposed one old lifecycle expectation that applied an option horizon to default price focus. Only ScreenContextLifecycle.test.jsx was updated: qualified SPY map ownership still clears on chain replacement; default QQQ price asking uses navigation-only version one/all; explicit map focus then submits the complete QQQ version-two record with days:7. All original clearing and selected-map assertions remain, and the submitted full record is compared in full. The focused lifecycle/Stock/Provider run passed 167 tests across three suites (overlaps the earlier Stock 115); full-frontend rerun remains main-task owned.

## Current checks and limits

Independently run after this correction: six frontend suites, 83 tests, all passed. They cover actual parent context hooks, old SPY to Extra NVDA, navigation-only study changes, memoized complete rich-record preservation, ticker changes, StrictMode and later-owner release. Backend acceptance probes passed for both pages. Receipts and source hashes are in C:/Users/DARK HERO/AppData/Local/Temp/floww-navigation-context-20261007/.

The missing direct guards are now closed: the family check explicitly includes the NodeConfluence test child; real GammaRegimeBanner is exercised with a supplied regime and remains the same DOM reading after changing studies; real CharmDecayPanel consumes a supplied expiry grid and preserves its reading after leaving and returning. An integration test mounts the actual App Options branch and checks every one of the 25 former side-column studies in its actual family, using isolated stateful child controls (the inline VelocityGauge is real). It verifies visibility and preserved control state, rather than comparing source-name snapshots. These guards establish reachability/composition/state; they do not certify the widgets' calculations or actual-provider data. The final three Directory/Picker/Options suites passed 53 tests. Six navigation/study/chat suites passed 86 tests after these additions; counts overlap.

Preserved populated screenshots were reopened: floww-options-functions-audit.png, floww-extra-functions-audit.png and floww-chat-controls-audit.png. They show the selector, levels/income screens and pre-fix Chat mismatch. Market/Volatility captures remain in the same temp folder. A screenshot alone does not prove an action, freshness, or final-source behavior. The older floww-other-tabs-audit-20261007.md concerned an earlier unreachable-provider review and must not replace the later actual-data pass.

Native chart export/download and screenshot actions are undergoing a separate main-task comparison; retaining the chart component does not establish that every native chart action survived.

The main task will check the current compiled app across Stock, Market, Options, Extra and Screener, plus shared Chat/search, with representative actual data and network failures. This source audit and 83 focused checks do not establish that final combined browser result.

## Related comparison peer handoff

Independently ran tests/related: 36 passed, with existing deprecation warnings. Source review confirms exact adjacent-session return pairs, no missing-date bridging/forward fills, minimum 20 pairs, partial longer-window labeling, unknown zero variance, own source/receipt clocks, all cached candidates ranked before paging, separate verified product membership and measured correlations, and explicit caret-symbol refusal without proxy substitution. Registry membership does not imply price availability. This is source/test evidence, not actual-provider proof.

Three isolated concrete findings were sent to the owner before freeze:

1. Expired-broker refresh can fail once in _get_broker then retry auth in real get_bars: two reserved calls versus three outbound calls.
2. GET of an existing closed WAL cache creates -wal/-shm side files despite mode=ro; the missing-file GET test missed it.
3. A slow failure uses its start clock for retry timing, allowing the cooldown to expire before the failure completes.

Receipts: related-auth-retry-peer-probe.txt, related-readonly-files-peer-probe.txt, related-failure-cooldown-peer-probe.txt in the navigation-context temp folder. This reviewer changed no Related source. The owner corrected all three issues. Independent original probes now show reservation three for three outbound calls, no new cache side files, and a deferred retry with zero calls after a slow failure. An expanded run caught one dated token-expiry fixture crossing the real near-expiry boundary; the owner made that fixture clock-independent. Final independent rerun: 39 passed, zero failed, with existing deprecation warnings. All three original independent probes pass, and no further concrete blocker was found in this scoped review. Receipt: related-final-independent-tests.txt. Actual-provider and compiled UI proof remains owned by the main task.

## Related local warm access review

The main task reproduced a global-key refusal of the new bounded Related warming action. Its correction adds an exact POST /api/related/{canonical uppercase symbol}/warm exception through existing require_local, plus the same check inside the route before provider work. No PublicPaths entry, key-check branch or order authorization was widened. Direct loopback client, localhost Host, exact trusted browser Origin, explicit local deployment and absence of forwarding headers are required.

Independent read-only review of auth.py, the route and existing local-access boundary found no new concrete blocker. Independently ran the ten new local-access tests: 10 passed, with existing deprecation warnings. The tests refuse remote/foreign/absent origin, forwarded callers, extended/traversal paths, other mutation methods and order paths, and prove the route blocks remote access before its work helper. No source edit was made by this reviewer. Receipt: related-local-access-independent-tests.txt.

## Scope preserved

No existing user job/window was stopped or replaced; no active data migration, new account/provider, budget increase, model-feature change, order, journal/paper work or phone work was activated. Paused scope remains paused. Keep this exact original-to-current mapping and focused regression guards together when changing layout, so reducing visible clutter cannot silently delete a critical tool.


Final root integration receipts: see 2026-10-07-screener-related-restoration.md. The formerly pending actual export, combined study/navigation, stock directory and related-price checks were exercised on the compiled app. Source-level mappings and independent checks remain distinct from provider freshness and whole-market completeness.

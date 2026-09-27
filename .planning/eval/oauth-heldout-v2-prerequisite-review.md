# V2 prerequisite review

Reviewed 2026-09-11 UTC. Read-only review; no model/provider calls, source edits, bindings, or evaluation runs. Cases remain frozen and UNBOUND/NOT_RUN. Only v2 cases and the two expressly supplied real acceptance exports were inspected; no v1/development questions or answers were opened for this task. Within the supplied exports, review used screen context and saved snapshot facts, not candidate prose or scores.

**More model allowance alone cannot complete this set.** The supplied exports contain three SPY observations only. They contain derived research snapshots and screen metadata, not original complete option-chain payloads or complete versioned map responses. They do not supply DIA, IWM, QQQ, or AAPL evidence, owner-isolation state, dispatch recording, or the required historical screen events. Missing prerequisites must remain not_assessable in the denominator, as frozen rules require.

## Case mapping

“Available” below means a supporting observation exists, not that the case has been bound or passed. Every actual execution still needs the frozen clock, identical evidence for both arms, and the controlled recording environment.

| Cases | Evidence now / missing prerequisite |
|---|---|
| price_01, price_02 | Missing DIA and IWM quotes. No substitute ticker is valid. |
| price_03 | Real conflicting SPY selection exists; QQQ quote is missing. |
| explain_04 | Available SPY estimated gamma facts (nonempty, degraded). Preserve unknown chain time and stale price. Original chain still needed for replay through current reads. |
| explain_05 | Missing DIA price and scalar-flip presence/quality assessment. |
| explain_06 | Missing IWM snapshot and confirmed stored-alert presence/absence. An empty SPY eligible-flow list is not an IWM storage check. |
| explain_07 | Missing QQQ contract count and expiry facts. |
| explain_08 | Latest SPY snapshot explicitly reports missing verified IV/price/expiry inputs and daily bars. This supports an honest limitation answer; original input payload is still needed to freeze exact field absence. |
| compare_09 | SPY evidence exists; DIA evidence missing. |
| compare_10 | Real conflicting SPY screen exists; IWM evidence missing. |
| compare_11 | All three requested snapshots (DIA, QQQ, IWM) missing. |
| expiry_12 | SPY saved coverage excludes 2026-09-18. The older actual screen selected 2026-09-14, satisfying a different-expiry context possibility. Requires deliberate frozen binding and original chain; do not turn the displayed map expiry list into chain coverage. |
| expiry_13 | Missing QQQ evidence and actual available-expiry list. |
| expiry_14 | Missing IWM evidence; evaluation clock still unfrozen. Saved SPY calendar version is exchange-calendars-4.13.2/XNYS, but it does not establish IWM coverage. |
| expiry_15 | Missing DIA snapshot proving actual absence of 2030-01-18. |
| map_16 | Heatseeker SPY query/version/visible scope exists, but selectedStrike and selectedExpiry are null. No real selected nonempty cell or full response captured here. Older selected SPY contract is on another page and outside that older visible map's strikes. |
| map_17 | Missing QQQ flowseeker-pro map, broad-scope flip, and requested-expiry context. |
| map_18 | Missing actual IWM screen/version and proof of genuine replacement/unavailability. Cannot manufacture a cache mismatch. |
| map_19 | Missing DIA Ask-time screen and later changed screen with actual event order. |
| history_20 | SPY current evidence exists; must create/verify controlled owners with no prior owned observation before both arms. Export alone does not prove owner history absence. |
| history_21 | Missing QQQ current evidence and owner history audit against the exact required previous close. A new verified empty owner could satisfy the negative history predicate, but is not yet established. |
| history_22 | Missing two genuinely recorded owned IWM observations with differing coverage. The different SPY observations cannot replace them. |
| source_23 | Missing DIA chain proving receipt present/source time absent. SPY's unknown chain time cannot stand in for DIA. |
| source_24 | Saved SPY map prices have known stale price times, but map exposure source observation time is unknown. Thus these exports do NOT prove the frozen predicate of a stale map with an original map-source time. Do not borrow price time or map build time to establish exposure age. |
| source_25 | Missing IWM snapshot proving the required input absence. Current adapter omits verified product expiry instant, so this negative case is plausible after an actual capture, not satisfied now. |
| unsupported_26 | Missing QQQ evidence. Executable option-entry proposals remain unsupported, which is the intended limitation being tested. |
| unsupported_27 | No AAPL snapshot in these exports. Frozen case permits actual absence, but the controlled read must verify it; company/news evidence is unsupported. |
| unsupported_28 | Missing DIA evidence. Calibrated event probability/trade setup remains unsupported, as intended for this negative case. |
| limit_29 | No market-data prerequisite. Needs actual controlled ask route and observed limit rejection; no result recorded here. |
| limit_30 | SPY evidence exists. Effective limits, recorded dispatch/spend, order isolation, controlled owners and route execution remain unbound. |

## Production capability constraints

- `server.py` constructs `ResearchReads(peek_chain, peek_map, read_alerts)` without `read_daily_bars`. Realized-volatility helper exists, but production has no attached daily-bar reader. The supplied latest SPY snapshot confirms unavailable daily history. Realized volatility needs sourced, completed, consecutive exchange sessions with an explicit price basis; model allowance cannot supply them.
- `public_api_adapter.py` carries date-only expiry, calculated T, and quote-side times, but supplies no verified `expiry_instant` or separate IV observation time. `structure_reads.exact_expiry` refuses to infer a product cutoff. Implied move needs a same-strike/same-expiry ATM call-put pair, coherent fresh price/IV times and an explicit product expiry instant. The model cannot invent this input. Missing-input cases may still pass by refusing honestly; the v2 set does not demand a successful volatility estimate.
- Stored-history comparisons require actual owned prior snapshots and compatible coverage; previous-close comparisons require an exact verified closing observation. More calls do not create historical source observations retroactively. The IWM differing-coverage case specifically needs real observations, not synthetic alterations.
- Display-map reads require the exact original query, version and response. Visible scope in an export is useful evidence but does not reconstruct the complete raw map. A new capture is required for the selected-cell, QQQ scope, unavailable-version and changed-DIA-screen cases.
- Research can consume cached underlying prices, exposure estimates and timestamp-qualified stored alerts. It has no supported executable option-entry proposal, company/news evidence or calibrated event-probability claim. More calls should not bypass those limits.

## Minimum completion work

Capture allowed real DIA/IWM/QQQ evidence and required screen/history events; retain raw chain/map payloads with original timestamps and absent fields; establish isolated owners and recording; freeze one evaluation clock and binding file before running either arm. Resolve source_24 using genuinely timestamped map evidence or retain not_assessable. Preserve every unmet case in the 30-case denominator. Only then can additional authorized model allowance address the remaining call-count constraint. This review does not authorize calls or certify acceptance.

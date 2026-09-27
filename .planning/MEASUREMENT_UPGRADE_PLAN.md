# Measurement upgrade and comparison plan

Date: 2026-09-27. Status: proposed plan; no application formulas or settings changed.

## Decisions and goal

Priority clarified 2026-09-27: focus on actual market-data legitimacy, math, precise readings and backend/frontend consistency. Paper/demo trading enhancements are deferred.

Cover all displayed readings, using current data sources only. No new subscriptions, paid feeds, increased provider limits, or trading activation. Improve mathematical correctness, clarity, consistency and responsiveness; claim better trading usefulness only after a separate historical evaluation. There is no universally best formula for different quantities.

The deliverable is a measurement inventory, verified calculation definitions, selectable valid methods and assumptions, a same-snapshot comparison view, and a measured rollout. Success means each displayed number can be traced to its inputs, reproduced independently and compared without moving prices or changing contract coverage hiding the difference.

## Starting evidence and limits

These are source observations, not an assertion that all displayed measurements have already been audited or that the paths below are all mounted today.

| Inspected area | Current evidence | Planned treatment |
| --- | --- | --- |
| backend/domain/exposure_metrics.py | Raw open-interest gamma, delta-weighted gamma, session-volume gamma and window activity coexist | Keep quantities separately named; do not rank them as accuracy levels |
| backend/routes/exposure_profile.py and backend/services/squeeze_exposure_profile.py | Route fetches up to four expiries and supplies 30/365; service uses that same time for each contract's implied volatility and shifted gamma | Reproduce on mixed expiries; use each contract's actual expiration/settlement time; make coverage explicit |
| backend/bs_greeks.py and backend/domain/greek_scalers.py | Vanna, charm and gamma comments contain conflicting unit descriptions; charm helper includes a 0.01 scaling and another helper divides it by 252 | Independently derive units, time direction and finite-horizon changes; trace actual callers before classifying each displayed result as wrong |
| backend/services/gex_vex_calculator.py versus canonical exposure path | Older VEX path uses vomma where canonical VEX uses vanna | Trace reachable consumers; separate the distinct sensitivities and version changed meanings |
| backend/services/gex_history.py | Historical/model feature convention differs from display convention | Preserve existing training features and stored history; any feature change needs a separate version and validation |
| frontend/src/components/SettingsPanel.jsx and flowseeker/TidehunterSettings.jsx | Existing settings cover refresh, layout and screens | Add a dedicated measurement section; preserve unrelated saved settings |
| frontend/src/components/SidebarPanels.jsx | Displays flips, levels, scenario labels, risk summaries, implied moves and volatility analytics | Audit upstream calculations and downstream claims together; assumed signs cannot establish actual dealer behavior |

The full inventory and live source-capability audit remain the first implementation deliverable. Presence of a connector or formula file is not evidence that its data is available or the calculation is displayed.

## Coverage inventory to complete first

Traverse every mounted tab, sidebar, drilldown, table, tooltip, chart, export, replay and generated research summary. Include portfolio, paper and forecast readings when displayed, without enabling trading or rebuilding deferred features. Maintain one row per distinct quantity, with all display aliases and callers attached. Mark dormant code separately.

| Family | Required audit and improvement |
| --- | --- |
| Option price sensitivities | Delta, gamma, vega, theta, vanna, charm and higher derivatives: units, sign, price model, exact remaining time, exercise style, settlement, dividends, interest rates and contract deliverables |
| Exposure and activity | Gross and assumed-net gamma, delta exposure, volatility/time exposure, open interest, daily volume and window changes: separate stocks of positions from trading activity |
| Levels and scenarios | Walls, flips, gaps, floors/ceilings, max pain, concentration and price-shift curves: derive from the chosen underlying quantity; report missing/multiple roots and scope limits |
| Flow and liquidity | Premiums, put/call ratios, bid/ask trade direction, flow scores and liquidity estimates: deduplicate, timestamp, identify coverage, handle corrections, zero denominators and uncertain trade direction |
| Volatility and distributions | Implied/realized volatility, skew, term structure, expected moves and option-implied distributions: consistent horizons, calendars, units and model assumptions |
| Scores, forecasts and risk | Composite scores, confidence, rankings, scenario text, position/risk and performance figures: document components, avoid double-counting, distinguish score from probability, check fees and marks where relevant |

Per row record: visible label, source/caller, formula, units, required inputs, timestamp, contract population, coverage denominator, sign assumption, missing behavior, method version, downstream dependencies and verification case. All displayed rows must be accounted for; uncovered rows remain explicitly unfinished.

## Input quality before alternative formulas

Use actual fields supplied by existing sources and saved captures. Confirm quote time, underlying time, open-interest date, expiry/settlement time, exercise style, delivered shares/cash, rate/dividend assumptions, valid bid/ask, implied volatility, Greeks, volume correction behavior and trade-side evidence. Do not print credentials or increase limits.

Separate source-provided Greeks from recalculated Greeks and show provenance. Compare them only after aligning units and assumptions. Recalculation is not automatically more accurate: European Black-Scholes is a useful reference, but American exercise, dividends and adjusted contracts need supported treatment. Where current data cannot support a model, label the approximation or make that method unavailable. Never silently invent a 30-day expiry, 20% volatility, 100-share deliverable, option type or zero for missing data.

Use exact remaining calendar time with explicit product settlement rules. Handle expired contracts and the expiry boundary explicitly; do not clamp all near-expiry contracts to an arbitrary day. A trading-session horizon must use its actual elapsed calendar time, including overnight/weekend intervals where applicable.

## Calculation definitions to prove

Notation: S is underlying price; m is verified contract size for standard contracts; OI is open interest; N is a signed contract count under a named assumption (or verified position if actually available). Delta and derivatives are per option share. Volatility is decimal, so one volatility point is 0.01. Formulas below are proposed definitions derived from these units, not newly verified implementations.

| Reading | Proposed definition / boundary |
| --- | --- |
| Gross gamma | Sum(abs(gamma) * OI * m * S^2 * 0.01); unsigned sensitivity scale per 1% underlying move, not a dealer position |
| Assumed-net gamma | Sum(gamma * N * m * S^2 * 0.01); name the call/put or other sign assumption. Hedge response has opposite sign under a delta-neutral hedge assumption |
| Delta exposure | Sum(delta * N * m * S); keep signed and gross views separate |
| Volatility-driven delta change | Sum(vanna * N * m * S * 0.01), with vanna = d(delta)/d(volatility); label per +1 volatility point, not per +1% stock move |
| Time-driven delta change | Prefer Sum((delta at t+h - delta at t) * N * m * S) for the declared horizon, holding stated inputs fixed. Check small-horizon limit against charm = d(delta)/d(calendar time). Do not confuse with theta or apply an unexplained 0.01/252 |
| Vega and theta | Vega * N * m * 0.01 is first-order option-value change per +1 volatility point. Theta is option-value change over explicit elapsed time, distinct from charm's delta change |
| Higher-order sensitivities | Keep each derivative distinct. For volatility curvature P&L, second-order term is 0.5 * vomma * N * m * (volatility shock)^2. Do not relabel vomma as vanna |
| Finite price/volatility/time scenarios | Reprice consistently using each contract's inputs; state frozen-volatility or supported surface behavior. Label full scenario change separately from local derivative approximation |

Adjusted/nonstandard contracts require a deliverable-aware valuation, not merely substituting another m. Unsupported cases contribute to reported missing coverage.

Volume-weighted and delta-weighted gamma remain separate descriptive activity/weighting choices. They do not reveal signed dealer holdings. With current inputs, dealer-position methods stay unavailable unless participant identity, opening/closing evidence, venue coverage and a defensible starting book are actually established. Otherwise offer clearly labeled sign scenarios, not fake confidence percentages.

Flip calculations must re-evaluate the chosen signed exposure across the price grid. Distinguish a crossing across strikes at current spot from a repriced zero-gamma underlying-price level. Report no crossing, multiple crossings and unstable roots. Max pain is an expiry payout calculation, not a promised price target. Option-implied distributions are risk-neutral model outputs, not calibrated real-world probabilities.

## Settings and fair comparison

Add Measurements within existing settings. Offer Current method, Candidate method and Compare for each compatible reading; group saved choices into named presets. Candidate means available for testing, not proven superior. Keep the safe default until its acceptance gate passes.

| User control | Allowed effect |
| --- | --- |
| Reading choice | Position-based versus activity-based quantity; units and names change visibly |
| Calculation source | Verified source Greeks versus supported recalculation, with model assumptions shown |
| Position assumption | Named call/put convention or explicit scenario; actual dealer mode disabled without evidence |
| Contract selection | Same ticker, strikes and expiries on both comparison sides; show excluded and missing coverage |
| Scenario | Price move, volatility-point move and elapsed time; advanced assumptions clearly marked |
| Saved choice | Save/reset presets and compare current versus candidate without silently changing the default |

Truth is not optional: no setting can turn missing data into zero, erase stale-data warnings or label an assumption as a known holding. An old method with a proven defect can remain as a labeled research reference, not an unlabeled trading default.

Freeze one immutable input snapshot and run both methods on it. Show values, absolute difference, relative difference only with a meaningful nonzero denominator, sign changes, level shifts, units, timestamps, assumptions and coverage. Compare formulas on the common eligible contract set; show differences caused by coverage separately. Different quantities may be inspected together but cannot be scored as interchangeable versions of the same number.

Every response, cache key, saved result and export must retain snapshot identity, method version, assumptions, scope, input policy and units. Reject stale results after setting changes. All linked panels and research explanations must follow the selected method or clearly declare that they do not support it; never combine incompatible methods silently. Preserve older saved results with their original definitions.

## Proving correctness and usefulness separately

1. Reproduce suspected defects with small independent cases before changing them. Test mixed expiries, put/call signs, long/short cases, units, dividends, settlement times, adjusted contracts, near-expiry behavior and missing versus true zero.
2. Verify sensitivities independently from option prices/deltas using finite differences and step-size convergence. Include analytical identities, per-contract manual examples and agreement across Python/accelerated implementations where used. Set absolute/relative tolerances before accepting results; near zero requires absolute error checks.
3. Test aggregation invariants: totals equal included contributions, reordering/partitioning cannot change results, same snapshots reproduce exactly within tolerance, coverage losses remain visible, and changing a setting changes every intended consumer.
4. Exercise actual mounted screens with recorded representative inputs: side-by-side values, rapid setting/ticker changes, expiry selection, reload, save failure, missing fields, replay, export and generated research. Tests of helper functions alone are insufficient.
5. Evaluate trader usefulness only where real historical inputs exist. Freeze a per-reading target and horizon before tuning; split chronologically, keep a final untouched period, prevent overlapping-label leakage and future-data use, and report all days including failures/unavailable readings. Present per-day results and uncertainty, not only pooled trades or selected wins. Compare with current method and a simple no-signal baseline. Claimed trade returns include costs and slippage.
6. Treat too little historical coverage as inconclusive. Start forward observation with existing access; do not reconstruct unavailable historical holdings from today's chain or promise an edge from mathematical correctness.

A method may be mathematically correct yet add no predictive value. Correct a proven arithmetic/labeling defect regardless of backtest profitability. Promote a predictive default only when the predeclared held-out evidence supports it; otherwise retain the current valid default or keep both explicitly experimental.

## Speed work and rollout order

Baseline request count, elapsed time and memory on fixed small/large snapshots before optimization. Reuse validated contract preparation, share Greeks across panels and cache by the complete calculation identity. Compute comparison from one fetch. Consider vectorization or existing acceleration only after parity passes. Target no material latency regression for normal single-method use; freeze a hardware-specific budget before implementation. Report measured median and tail times, not an unsupported speed claim.

| Order | Deliverable | Completion check |
| --- | --- | --- |
| First | Full display/source inventory and defect reproductions | Every active displayed reading has a record; missing inputs and existing-data limits are explicit |
| Second | Verified foundational calculations and versioned definitions | Independent formula/unit tests, actual caller checks and preservation of saved/model meanings |
| Third | Measurement settings and same-snapshot comparison | Browser evidence of fair comparisons, consistent consumers, saved choices and honest unavailable states |
| Fourth | Historical/forward evaluation | Predeclared targets, untouched evaluation data, coverage accounting and reproducible outcomes |
| Fifth | Speed improvements and gradual promotion | Before/after timings, parity, rollback and explicit reasons for each promoted default |

Inventory and source capability checks can proceed independently. Formula work follows those checks. Comparison layout can be designed after definitions, but cannot be accepted before calculation identities exist. Independent review challenges definitions and test oracles before promotion.

Keep reversible method selection and versioned saved outputs. No active app/session restart or deployment is included. The user subsequently authorized committing this plan as part of main reconciliation. Writing or saving it does not implement the measurement upgrade.

## Primary references

- Cboe, market-maker net gamma and the difference between gross volume and net holdings: https://www.cboe.com/insights/posts/volatility-insights-evaluating-the-market-impact-of-spx-0-dte-options (read 2026-09-27). Supports the need for position evidence; does not validate this application's estimates.
- Options Industry Council, gamma: https://www.optionseducation.org/advancedconcepts/gamma (read 2026-09-27). Sensitivity definition and long/short sign distinction.
- Options Industry Council, vega: https://www.optionseducation.org/advancedconcepts/vega (read 2026-09-27). Volatility sensitivity.
- Options Industry Council, theta: https://www.optionseducation.org/advancedconcepts/theta (read 2026-09-27). Time sensitivity of option value.

Higher-order formulas above must receive independent derivative checks during implementation; these introductory references are not cited as proof of every formula.

## Plan review

Independent read-only review completed 2026-09-27 02:39 UTC with no material concerns. Reviewer confirmed fair comparison design, current-data limits and separation of calculation correctness from trading usefulness. This is review of the plan, not acceptance of unimplemented formulas. Application files remain unchanged.

## Durable-save update

2026-09-27: User requested this plan be saved with the reconciled main branch. This file is the durable tracked entry point. The plan remains proposed; reconciliation of existing work does not implement the measurement upgrade.

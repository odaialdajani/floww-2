# Prepared paper risk gate design review

Reviewed 2026-09-27 UTC. Read-only source review of accounting, execution, valuation, observation service, prepared service, repository commit, and plan sections 10.2/10.3. No providers, models, orders, source edits, or activation.

## Decision summary

This is an unfinished admission requirement in explicitly unmounted, default-denied preparation, not a newly enabled trading regression. The next prerequisites are (1) a full approved account policy, (2) verified proposal loss and entry/exit/lifecycle cost evidence retained with orders/holdings, and (3) risk checks at both staging and later fills under the same version-checked account change. No limit values or activation are proposed.

## Recommendation

The smallest sound next preparation is an immutable explicit account-policy record plus an independently verified trade-risk record, with missing evidence represented as unknown and entry refused. Then a pure decision can run over the exact current account and the proposed staged state before their single version-checked commit. A boolean callback or the saved observation's limits_passed field is not this contract.

No capital, limit, cost bound, lifecycle assumption, or live/paper authorization should be invented. Existing slippage selection remains unchanged.

## Required persisted records

| Record | Concrete fields | Required meaning |
| --- | --- | --- |
| Account policy | policy_id, policy_version, policy_digest, owner, account_id, venue, epoch, currency, effective_at, accepted_by, acceptance_evidence | Full immutable policy body, owner-authorized, bound to this account/recovery. Every change advances account version and requires fresh observation; never silently reset same-session risk anchors. |
| Explicit limits | per_trade_max_loss, daily_loss_limit, observed_drawdown_limit, max_committed_exposure | Exact decimal amounts in the account currency. Missing values refuse. Zero loss limits mean no new exposure, not disabled protection. Metric definitions and comparison boundaries are part of the policy version. No defaults are supplied by this review. |
| Valuation policy | mark_method, max_mark_age_seconds, max_spread, peak_coverage | Persist full existing mark-policy choices. peak_coverage must explicitly describe sampled observations; it cannot mean continuous intraday high. |
| Session evidence | session_id, calendar_version, session_digest, opened_at, closed_at, opening_equity_evidence | Trusted exchange-calendar/session source and actual opening-equity source. A first mid-session request is never substituted for the open. |
| Verified trade risk | proposal_id, proposal_version, proposal_digest, economics_digest, binding, currency, product_kind, contract evidence, maximum_loss, maximum_loss_basis, entry_cost_bound, exit_cost_bound, lifecycle_cost_bound, verified_at, valid_until, verifier_version, evidence_ids | Server-derived evidence binds exact confirmed quantity, contract, premium factor, limit, fees, chosen slippage, deliverable and lifecycle. Unknown exit/lifecycle cost is not zero. The original approved loss budget and remaining exposure have different meanings. |
| Decision receipt | policy version/body or immutable reference+digest, input_account_version, book_digest, observation digest/version, session digest, trade-risk digest, evaluated_at, valid_until, exposure_before, exposure_after, reserved_before, reserved_after, available_cash_after, loss_from_open, observed_drawdown, decision and reasons | Save with order and reservations in the same account change/event. It describes a decision on these inputs, not a reusable approval token. |

The policy should be stored in the same account state protected by its version check. An external mutable policy record would require its own atomic consistency proof. Do not add duplicated policy knobs when the current mark-policy fields can be reused under the same immutable policy body.

## Admission invariants

1. Request owner/account/venue/recovery equals the account, policy, saved observation, confirmed proposal and risk evidence. The selected venue stays internal; current prepared service methods rely on repository defaults and do not establish multi-venue composition.
2. The operation expects the version just read. Reuse receipt-first retry behavior, including the observation service's second receipt lookup for a winner between receipt/read. A competing stage/fill/policy change wins once; the loser fails and obtains fresh evidence. Never automatically replay a rejected stale decision.
3. After all awaited external checks, use one trusted decision time. The saved observation must be current for the exact book/version/binding, before its validity deadline, with no unknown holdings, known equity, observed risk, and matching full policy/session evidence. A stale last_complete amount is display-only. An unknown session/lifecycle/cost obligation blocks increased exposure.
4. Independently recompute loss from verified opening equity and observed drawdown from the retained sampled peak. Loss equals max(0, opening equity minus current equity); observed drawdown equals max(0, sampled peak minus current equity). Require strict less-than for the existing loss/drawdown boundary convention; exposure at the configured cap may pass. A future policy must explicitly preserve/change these semantics. Preserve peaks through missing evidence, policy changes and restart. Do not claim a continuous maximum.
5. Produce candidate state using the existing pure stage transition, then run the deterministic risk decision before committing it. No state mutation escapes on refusal. Cash, lots and equity do not change merely because an order was staged.
6. Recompute all remaining reservations from working orders, including partially filled remainders, using verified immutable order economics; do not trust an arbitrary supplied sum. Each buy's remaining reservation is quantity times (premium factor times limit + per-unit fee + enabled cash-method slippage). Price-method slippage is already inside the effective fill-price limit and must not be added again. Filled quantity is represented in holdings/cash, never again in pending reservation.
7. Existing marked long holdings stay in exposure even while a sell is pending. Pending sell proceeds do not finance new buys. Working exit cash shortfalls and separately proven exit/lifecycle obligations consume their appropriate cash/risk buffers; cancellation or an uncertain lifecycle does not pretend those obligations vanished.
8. For the smallest conservative stage metric, use marked holdings plus all remaining committed entry debit plus required exit/lifecycle buffers. Record its name/meaning explicitly as committed exposure; it is not delta exposure or a proof of contractual maximum loss. Existing valuation's known_holdings_value + reserved_cash is reusable only for the currently represented reservation subset. Enforce per-trade independently verified maximum loss separately.
9. Available cash after staging is current cash minus all remaining reservations and explicit required buffers. Do not subtract reserved principal from marked equity or treat it as realized loss. Future fees/cash slippage/spread-to-mark changes belong in a separately defined projected-cost check if policy requires it; they cannot be invented from current equity. A risk policy choosing such a check must define inputs for both existing pending orders and the candidate.
10. Persist decision provenance, order, reservations and event together through the existing conditional account-version update. Account/version equality protects state concurrency but not time passing: define the authoritative write-time freshness condition (or explicitly label decision-time semantics and recheck before fills). Slow storage must not turn an expired decision into fresh authority.
11. Default-denied production composition remains in place. Passing this deterministic check is necessary evidence, not permission to bypass release acceptance, trusted proposal construction, exact human confirmation or supported lifecycle rules.

## Reuse and limits

- accounting.exact/derived/exact_context preserve monetary digits; simulated_fill already prevents charging the chosen slippage twice.
- execution.stage_order creates prospective reservations, distinct structures and prepaid exit capacity; fill_order limits cash debit to the saved entry reserve and reduces only the remaining reservation after a partial fill.
- valuation.current_observation binds version, book, owner/account/venue/recovery and source/session/product deadlines. Observe retains unknown counts, anchors and sampled peaks.
- observation_service freezes checker inputs and commits observations with their history; repository.commit supplies owner/venue/recovery/version comparison and idempotent receipts.
- The current observation persists policy_digest, not the full policy body/version/acceptance. Current pending orders persist proposal_digest, not verified maximum-loss, lifecycle and exit-cost evidence. These are concrete missing prerequisites.
- PreparedPaperService.quote can fill later without a risk/admission check. A stage-only gate cannot claim to prevent fills after loss breaches, policy change, session close or product lifecycle cutoff. New exposure at fill needs fresh bounded account/contract evidence and the same conditional write protection. Resting-order cancellation on a breach and risk-reducing exits need explicit behavior.
- Pure execution permits a closing order whose cash shortfall exceeds free cash; its stage cash-cap check applies only to buys. This is not an authorized debt policy. Future exit semantics must address insufficient fee cash while preserving safe risk reduction; do not hide this inside a new entry cap.
- Every economic change makes the current saved observation stale. Requiring a fresh observation before another entry is safe but should be explicit; do not silently relabel the old value current after staging/filling.
- Full lifecycle is still unimplemented for options; corporate actions/dividends are unimplemented for shares. Plan 10.3 blocks first product admission until that product's lifecycle behavior is specified and verified. A long option's paid premium alone does not prove safety through exercise/delivered shares.

## Required proof before claiming the stage check ready

Use synthetic owner-selected policy values only. Verify mismatched owner/account/venue/recovery/session/policy, missing/unknown/stale equity, each exact loss/exposure boundary, existing pending buys, partially filled remainders, pending exits, fees and both existing chosen slippage modes. Verify that reservations are not equity losses and no pending exit reduces current exposure. Verify concurrent entries/fills/policy changes, slow callback/commit crossing a deadline, duplicate retries, fresh-process reload of unchanged policy/peak, and refusal without any partial state write. Explicitly keep later-fill enforcement and product admission outside a stage-only completion claim.

## Open choices and blockers

The owner must supply/approve actual capital and risk limits, the chosen exposure definition, and any projected-cost rule. Independently verified proposal loss, exit costs, lifecycle handling, session/opening equity and policy acceptance records remain prerequisites. The review recommends preparing those contracts now while keeping every missing bound unknown; it does not recommend choosing numbers or opening production admission.

## Stage and later-fill decision boundary

Stage path: retrieve existing receipt; read exact account version; obtain trusted immutable proposal/confirmation evidence; take decision time after slow checks; require current complete observation and policy; create candidate stage; recompute candidate pending cash/exposure; save its decision, order and reservations with the account-version check. A denied candidate changes nothing.

Later-fill path: retrieve original receipt first; read the current account/version and current policy; independently refresh required marks, session and contract/lifecycle evidence; revalidate the working order's frozen confirmed economics and validity; compute the actual eligible partial fill using fill_order; value the complete prospective book using observe with verified full-account inputs; check cash/reservations, current loss and sampled drawdown, prospective exposure and trade/lifecycle obligations; save fill, prospective observation/risk anchors and remaining reservations in one version-checked account event. No prior stage decision substitutes for these checks. If the latest policy differs, require explicit reconciliation/renewed approval as defined by that policy; do not silently grandfather a stale order or reset the loss anchor.

The prospective post-fill check must include actual fees and the already selected slippage exactly once. It may also need a pre-fill risk breach check so an entry that happens to improve a mark does not bypass a policy that has already stopped new orders. The product/policy must define breach latching and reset authority if required; no latch or automatic reset is assumed here. Loss-reducing closes/cancellations need their own validated rules and must not inherit a blanket new-entry shutdown.

A fill's quote is not a complete set of marks for every holding. Without a trusted full-account valuation frame, the later-fill risk result is unknown. Missing/expired lifecycle evidence cannot be solved by consuming the quote and attempting to reconcile afterward.

## Independent exact cash scenarios executed

Evidence: [paper-risk-cash-scenarios-20260927.json](paper-risk-cash-scenarios-20260927.json). Pure synthetic functions only; all literal expected amounts passed. The following prices, fees and cash are test fixtures, never recommended account/risk settings.

Starting cash is 1000. Two long contracts use a verified test premium factor of 100, limit 2.10, fee 0.65 per contract, and the existing chosen adverse increment 0.05. One contract fills from ask 2.00, then is marked at bid 1.90.

| Quantity/cost fact | Price-method slippage | Cash-method slippage |
| --- | --- | --- |
| Cash after staging | 1000 | 1000 |
| Full entry reservation | 421.30 | 431.30 |
| Actual one-contract debit | 205.65 | 205.65 |
| Cash after one fill | 794.35 | 794.35 |
| Remaining entry reservation | 210.65 | 215.65 |
| Marked equity, including held value 190 | 984.35 | 984.35 |
| Free cash after remaining reservation | 583.70 | 578.70 |

Independent arithmetic: price-method full reserve is 2*(100*2.10+0.65)=421.30; cash-method reserve adds 2*100*0.05=10.00. Both actual fills debit 100*2.00+5.00+0.65=205.65, with the 5.00 charged through the selected representation only once. Equity is 794.35+190=984.35, not equity minus the remaining reservation. The two reserve values differ because the price-method limit already caps the adverse effective price; the cash-method fee is outside that price limit.

Exit-cost stress test: after buying one contract, cash is 794.35. A deliberately exaggerated but currently accepted fee of 1000 on a close limited at 1.80 reserves a cash shortfall of 820.00. Current pure stage accepts it; an eligible 1.90 bid fill produces cash -15.65. This independently demonstrates that existing close mechanics do not establish an approved fee-cash/debt rule. It is a prerequisite finding, not a reason to remove risk-reducing exit capacity or invent a fee cap.

## Sequencing without activating admission

1. Freeze the owner-approved complete policy contract, currency/metric semantics and policy-change behavior; leave unknown actual amounts absent and fail-closed.
2. Define verified proposal economics and independently justified entry/exit/lifecycle cost/loss records for each supported shape. Retain references with pending orders and held structures so restart/partial fills preserve their provenance.
3. Specify and verify product lifecycle behavior and insufficient-exit-cash handling. This may reveal required policy choices; return those choices to the owner instead of assigning values.
4. Implement bounded pure stage and later-fill risk decisions and isolated atomic-store proofs only once their required inputs exist. Preserve default denial and the separate research/proposal/human-confirmation/product-admission gates.

No policy record, risk gate or product lifecycle implementation was added during this review. Existing source behavior was read and independently exercised only in the synthetic cash examples above.

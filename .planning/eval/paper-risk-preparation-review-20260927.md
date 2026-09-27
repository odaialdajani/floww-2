# Independent review of unmounted paper risk preparation

Reviewed 2026-09-27 00:30 UTC. Scope: new policy.py, risk.py and focused tests; existing accounting/execution/valuation/repository contracts. No production/source edits, providers, models, account activation or real orders. Source identities: paper-risk-source-manifest-20260927.json; the reviewer independently matched all four hashes.

## Verdict

One material contract-linkage defect was reproduced, fixed by the implementation owner, and independently cleared. Nineteen focused tests pass on the reviewed revision. Additional independent synthetic close/cost and pending-contract probes pass. No additional blocking arithmetic defect was reproduced in this deliberately narrow pure preparation slice.

This does not complete admission. Trusted source/owner validation, durable observation handling on refusals, conditional persistence/freshness composition and actual product lifecycle support remain mandatory before activation. Every pure pass still returns admission_allowed=false; refused/unknown results expose no candidate state.

## Fixed finding: changed contract facts reused old risk evidence

Initial behavior: after staging the fixture option, change the later valuation metadata from cash settlement to physical shares, call to put, strike 100 to 1000, or underlying TEST to DIFFERENT. Every independent mutation returned pass and equity 984.35 against the unchanged original cost/lifecycle evidence. costs.contract_digest and lifecycle_digest were only format checked, not connected to actual frame metadata.

Evidence: paper-risk-contract-link-probe-20260927.json.

The revised code verifies full metadata content and the declared lifecycle subset against both saved evidence digests for every active held/pending contract, validates product metadata and bounds the decision by its product deadlines. Independent reruns of all four mutations now return unknown, no candidate and the contract/lifecycle mismatch reason. Pending-only missing metadata and an event due now also return unknown. Evidence: paper-risk-contract-link-recheck-20260927.json and paper-risk-pending-and-peak-probe-20260927.json. Focused tests also cover changed exercise cutoff, wrong lifecycle digest and pending-only deadline.

## Confirmed narrow behavior

- Policy fields/values and supported metric semantics must be supplied explicitly. There is no automatic capital or limit choice. Owner acceptance and trade-evidence factories require an exact True from detached trusted callbacks; record digests preserve content but are not signatures, authorization or proof of actual lifecycle support.
- Frozen economics and records bind owner/account/venue/recovery, exact policy and contract facts; working reservation amounts are recomputed from remaining quantities. Per-trade loss follows only the declared prepaid-long zero-recovery plus linear per-unit exit/lifecycle cost model.
- Stage and later-fill decisions revalue actual current and prospective books. An earlier stage pass is not reused as a later risk pass. Missing marks/evidence, mismatches, expired records and breaches return no candidate.
- Entry reservation is not subtracted from equity. Filled quantity remains in marked holdings while only the unfilled remainder stays reserved. Remaining exit/lifecycle buffers cover held plus pending quantity; pending sells do not release holdings or count sale proceeds as cash. Closing cash shortfalls remain inside the cost buffer rather than being added twice.
- An actual reducing close remains possible after a daily loss breach when evidence, cash and closing-cost bounds remain known. In independent price- and cash-slippage probes, two held contracts at a lower mark had loss 311.30; closing one changed cash to 633.05, cost buffers 14 to 7, committed exposure 114 to 57 and loss to 316.95 after real closing costs. Both returned preparation-only pass. Evidence: paper-risk-reduction-probe-20260927.json. The revised focused test additionally rejects a deliberately excessive closing fee.
- Exact arithmetic survives low ambient decimal precision in the focused regression. Negative resulting cash/free cash is refused under the explicitly chosen long_only_cash policy; this does not impose an invented general policy on other possible account modes.

## Open composition requirement: refused orders must not erase observed peaks

Independent demonstration: with cash 588.70 and two held contracts, a fresh mark of 3.00 gives actual equity 1188.70. A new-entry candidate exceeds the configured exposure cap and refuses with state=None/decision=None. Without separately saving that actual observation, a later 2.20 mark gives equity 1028.70 and the next entry passes with observed drawdown 0, although the drop from the earlier computed actual high is 160.00 and the fixture drawdown limit is 100.

Evidence: paper-risk-pending-and-peak-probe-20260927.json. This is an unfinished composition obligation in an unmounted pure component, not a newly enabled trading regression. The implementation owner explicitly retains separate durable observation handling as a prerequisite.

Before admission, trusted composition must persist the actual current-equity/session-peak observation even when a candidate order refuses, or retain an explicit unresolved state that prevents later new exposure until it is reconciled. Never save hypothetical post-fill equity from a refused fill. A returned actual-before observation could help a future composition, but returning a partial economic candidate on refusal would be wrong. For this pure slice, an explicit mandatory composition contract is sufficient; it is not evidence that the contract has been implemented.

Do not blindly insert an additional ordinary observation write before every risk-reducing close: at account/history capacity, it could block the prepaid exit path. Integrate actual-observation persistence with the existing reserved-exit capacity rules, and test refusal/restart/capacity ordering together before claiming durable account risk control.

## Remaining boundaries

Decision-time freshness is explicitly labelled; account version checks alone do not prove freshness after slow I/O. The eventual conditional commit/fill path must enforce its stated time semantics and use the exact state version that was evaluated. These pure modules do not authenticate callers, fetch/verify provider truth, save records, mount action routes, prove continuous intraday peaks, implement option exercise/settlement or share corporate actions, or unlock product admission.

Full metadata binding is deliberately strict. A refreshed metadata source/verification timestamp changes the full content digest and requires reverified trade evidence; it must not silently bypass or discard the mismatch. No automatic evidence-refresh/reconciliation workflow was established by this review.


## Final source and store follow-up - 00:33 UTC

The final risk.py changes since the arithmetic review are a required refusal-observation composition docstring and equivalent Ruff cleanup. No new economic behavior was introduced by that diff.

Initial real-store report paper-risk-store-20260927.json was inspected against verify_paper_risk.py. It uses a local store and a fresh isolated synthetic database. Two evidence gaps were returned to the owner for correction: the stage/fill competition reuses a single operation identity for two distinct commands, so it does not yet prove distinct operation identities competing at one version; and restart compares state/version but not event risk decisions or exact projected history, so the claim of exact decision recovery is not yet established by its assertions. These are proof-coverage findings, not observed persistence corruption. Stronger independent recheck pending any verifier revision.


## Final store-proof resolution - 00:34 UTC

Both preceding proof-coverage findings are closed. The revised verifier creates and asserts distinct operation identities for the stage/fill competition. Its restart snapshot contains exact pending events; the fresh child compares those events before projection, verifies the pending queue is empty afterward, and compares every sorted projected immutable event (including risk decisions) with the saved originals.

I independently replayed the final verifier in a fresh isolated database: all five claimed checks passed, process exit 0, no stderr. Evidence: paper-risk-store-independent-20260927-ba4109de.json (plus its restart sidecar). The owner's separate final run is paper-risk-store-final-20260927.json. These results support the stated synthetic policy/decision persistence, idempotent duplicate stage, distinct-operation version race, stale-version refusal, exact fresh-process reopen and event projection claims. They do not prove production authentication, provider truth, lifecycle implementation, refused-observation composition, all possible interleavings or write-time freshness; those limits remain explicit.

The review hash companion now identifies all four final files: policy.py, risk.py, focused tests and verify_paper_risk.py. No source edits were made by this reviewer.

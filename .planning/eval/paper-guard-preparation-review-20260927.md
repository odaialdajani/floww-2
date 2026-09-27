# Independent bounded guarded-paper review

Reviewed 2026-09-27 01:08 UTC. Scope: risk_assessment.py, guarded_repository.py, focused tests and isolated verifier. Source identities are recorded in paper-guard-independent-review-hashes-20260927.json. No source edits, provider/model calls, controller activation or production accounts.

## Verdict

The reviewed narrow preparation passes eight focused tests, an independent replay of all six isolated-store claims, and four additional actual-store concurrency/ambiguous-response checks. Three related finalizer linkage gaps were found during review and the implementation owner fixed them; independent adversarial rechecks now refuse all tested mismatches without a candidate. No additional blocking reserve/arithmetic defect was reproduced in the final reviewed revision.

This does not establish a mounted source controller, automatic historical reconciliation, live/paper authorization or product lifecycle support. The component is still a bounded preparation mechanism requiring trusted composition; its generic repository is not a public financial authorization endpoint.

## Fixed finalizer findings

1. **Missing/incomplete actual reading could clear uncertainty.** The initial finalizer accepted a non-pass result with actual=None, removed the intent and allowed later replenishment/new assessment. This violated the acknowledged unresolved fence. The final revision requires a complete actual snapshot, recomputes it exactly from the captured frame/current assessed book, and binds its time to the assessment. Missing, fabricated, mismatched and incomplete readings now retain the intent by refusing finalization.
2. **A reducing assessment could carry a new buy.** Independently reproduced a BUY candidate finalized under a reduce intent while an earlier entry intent remained unresolved. The new order was added and the original uncertainty did not prevent exposure growth. The final revision checks intended side and exact reducing structure and refuses this case.
3. **A passing result from different prices could replace the captured high.** Captured/actual equity was 1188.70, but a passing candidate separately calculated from lower prices saved equity and peak 1028.70 and added a buy. Scope, book and account version matched, so those checks alone were insufficient. The final revision fully recomputes the candidate from the durable captured parameters/evidence/order/quote/frame at the original decision time and requires exact result equality.

Evidence: paper-guard-candidate-frame-probe-20260927.json records the third acceptance. paper-guard-independent-recheck-20260927.json records the second acceptance during the intermediate revision. Final refusal evidence: paper-guard-independent-final-recheck-20260927.json and paper-guard-candidate-frame-recheck-20260927.json. The implementation was being edited during the earliest probe runs; the report distinguishes those intermediate results from the final reviewed files.

## Independent proof obtained

- Eight focused tests pass, including exact historical basis, real refused high/160 drawdown, current final observation binding, overlapping intent preservation, missing credits/oversized input, and the added linkage regressions.
- Fresh isolated replay: paper-guard-store-independent-20260927-92e5bf91.json, process exit 0, no stderr. The original six claims are supported: collection isolation; the full 128-event-plus-reservation budget still saves the refused actual high 1188.70; protected close staging/filling gives exact cash 633.05 and keeps that high; a fresh process reopens exact guarded state/pending bodies and projects exact history; failed post-begin writes keep the fence and normal frozen restore retains it; actual server predicates reject expired/future windows and accept a current window.
- Additional fresh isolated probe: paper-guard-race-response-independent-20260927.json. Two distinct begin identities based on the same account version yielded exactly one complete commit and one conflict. The winner blocked another entry assessment. Twelve identical retries returned the same receipt without consuming more credits. A wrapped write then succeeded durably and deliberately lost its response; the pending intent remained, and the original identity reconciled/retried without another mutation. This probe uses an empty synthetic frame strictly as unevaluated intent data; it makes no valuation/source-truth claim.

## Reserve and identity assessment

Guard credits remain included with execution recovery obligations in the stored reserved-event count. A begin consumes its assessment credit while leaving resolution funded. A refused resolution consumes its own remaining credit; a passing reducing transition uses its corresponding execution-event obligation, preserving future attempt capacity. Actual event pressure tests confirm the protected cases rather than merely checking constants.

Final control/credit changes are incorporated before saving the observation book digest and account version, so normal observation reads remain correctly bound. Separate collections prevent unchanged base services from discovering these guarded accounts. Historical basis excludes recursively nested control data. Old overlapping assessments remain unresolved after a version change; neither replenishment nor a later unrelated reading silently clears them.

The finite assessment budget is not an unlimited-exit guarantee. Exhausted/overlapping attempts and failed historical capture still need exact reconciliation/projection, which remains unavailable through a controller. Replenishment's caller obligation to prove exact projection is not itself production composition proof.

## Server time and recovery limits

The final code rounds the not-before bound upward and the expiry bound downward to BSON milliseconds, refusing collapsed windows. A passing risk decision supplies the bounds; optional caller values cannot broaden them. The actual-store proof supports these ordinary server-expression conditions. It does not establish lock-wait, retry scheduling or journal-acknowledgement-time freshness. Existing explicit wording correctly avoids that stronger claim.

The injected verifier failure occurs before the update, while the independent extra probe covers a successful BEGIN whose reply is lost. Neither establishes a complete controller crash/restart protocol for finding/reusing every resolution identity. Preserve stable resolution identities and exact assessment linkage when that controller is eventually designed; never infer refusal from a timeout or replay a new financial operation blindly.

Normal checkpoint/frozen restore preserved an unresolved intent exactly in the tested account. Frozen state and old source bindings are retained, not automatically reconciled or authorized. Tests do not prove all concurrency schedules, arbitrary byte-limit saturation, historical reconstruction after a real overlapping exit, or source/provider truth. These remain explicit limits, not grounds to call admission complete.

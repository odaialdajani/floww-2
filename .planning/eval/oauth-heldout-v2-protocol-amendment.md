# Prospective source-policy amendment for oauth-heldout-v2

Status: PRE_EXECUTION / UNBOUND / NOT_RUN.
This amendment changes only the evidence-source policy for the frozen 30-case set. It does not change any question, answer criterion, scoring scale, comparison rule, call allowance, or application source. No v2 deterministic or candidate answer has been run or examined during this preparation.

## Reason and authority

The authoritative plan, section 12, expressly allows recorded sanitized market fixtures plus deliberately synthetic failure cases labeled as such. The original v2 protocol's requirement that every scenario arise naturally in a new real Public capture is unnecessarily narrower than that plan.

This correction follows a requirements review before either v2 arm runs. It is not based on candidate outputs, observed v2 scores, or a wish to remove a failed case. The original cases, rubric and manifest remain unchanged and retained with their original hashes.

## Exact precedence

Only these source-policy restrictions are superseded:
- Cases file: binding_rules.source, binding_rules.negative_cases, and prerequisite/context phrases requiring a genuinely or newly captured real failure condition.
- Rubric: the Freeze before execution source restrictions and the requirement that all 30 cases arise from real conditions.
- Manifest: new_snapshot_requirement and prerequisite_policy restrictions that prohibit any synthetic failure condition.

The replacement is: bind actual recorded sanitized Public inputs for supported market facts; allow explicitly labeled controlled failure transformations or controlled screen/history setup where needed to exercise the same frozen case. Keep every original market input unchanged in an immutable source artifact. Save any transformed input as a separate derived artifact.

Every other requirement remains in force: exact literal questions and requested dates, independently checked answer expectations, both arms using the same bound inputs/clock, complete 30-case denominator, honest not_assessable status, grounding/scope/ownership/order/budget checks, real model-dispatch evidence, usefulness comparison, exposure rules and explicit authorization. If a case still lacks enough supported evidence to test its intended requirement, it remains not_assessable. Synthetic data may not be used to fabricate a positive real-market capability or hide missing coverage.

## Binding and labeling before either arm

For every case, freeze:
- Evidence class: recorded_public, recorded_public_controlled_context, or synthetic_failure_from_recorded_public.
- Original sanitized Public file and SHA256, genuine source and receipt times, and actual absent fields.
- Evaluation clock and calendar identity. A historical replay clock is allowed and must be labeled historical replay; it never changes the original observation time or proves present freshness.
- Exact original screen/contract/expiry/map selection and any controlled changes, with event order.
- For transformations: source-file hash; derived-file hash; deterministic recipe; every altered, removed or added field with before/after values; artificial-time declaration; and the failure condition being tested.
- The expected scope, numbers, unavailable state and refusal reason, independently derived from the bound original/derived inputs before either answer is captured.
- Equivalent isolated owner-history state for both arms.
- The cases, rubric, original manifest, this amendment and its hash-record SHA256 values in the final binding.

The same derived artifact and clock go to both arms. Do not use the application's answer text as an expected answer. Check arithmetic, date/session selection, missing-data behavior and selected-cell values independently. Preserve the original raw evidence even when a transformation removes a field from the derived fixture.

## Permitted case-specific construction

Positive cases price_01 through price_03, explain_04 through explain_08, compare_09 through compare_11, expiry_12 through expiry_14, map_16 and map_17 use recorded Public market facts and real captured map structures. Controlled question/screen selection is permitted and labeled. Do not fabricate a price, gamma, flow, volatility, settlement time or healthy quality to make their positive prerequisites pass. A naturally absent input can support the already-frozen conditional abstention criterion.

expiry_15 may use recorded absence of the exact requested expiry. If necessary, a separate derived fixture may remove only that expiry's contracts to test the no-substitution failure, explicitly labeled synthetic. The question date never changes, and an empty scope must not be represented as measured zero exposure.

map_18 may model an unavailable exact map version by controlling the cache lookup result or selected version. Retain the real underlying map unchanged and label the cache/version condition synthetic if it was not observed naturally. Expected behavior remains no silent replacement.

map_19 may replay an actual recorded screen/map and then change the screen through the real interface or controlled UI fixture after Ask. Freeze the before/after contexts and event order. An automated fixture is not proof that the user performed the sequence on a live market display.

history_20 can use an empty controlled owner history. history_21 can use recorded owned observations with the exact required close deliberately absent. history_22 can use separately labeled history records derived from real recorded observations with a documented contract/expiry coverage subset. Do not invent past prices, source times or an observed market change. The desired result remains honest inability to compare when history is absent or incompatible.

source_23 may preserve a naturally unknown chain source time; if it is known, a derived failure fixture may remove it while retaining the real receipt timestamp. Mark that removal synthetic, and expect unknown source age. Receipt time is never converted to source time.

source_24 MUST be bound as an explicitly synthetic stale-map failure in this protocol. Begin from an immutable recorded Public map and retain all market values. In the separate derived fixture set the map's source observation field to an explicitly artificial instant at least ten minutes before the fixed evaluation clock; record that field as artificial in the transformation ledger. Use a clock-calculated test instant independent of quote, build, receipt or fetch timestamps. If another source-time field would take precedence, record and resolve that field explicitly so the intended stale-map path is exercised. Never copy quote time, build time, receipt time or a fabricated timestamp into the raw source artifact. This case proves stale-map refusal under controlled conditions, not that Public supplied an option-map observation timestamp, and not the real age of the recorded map.

source_25 may use actual missing implied-volatility/product-expiry evidence, or a derived fixture removing the required verified field. Never fill an absent product cutoff or volatility estimate. It tests refusal, not a healthy implied-move claim.

unsupported_26 through unsupported_28 use actual recorded evidence or its recorded absence under the current unsupported-capability contract. No invented company event, option premium, probability or stop is permitted. limit_29 needs no market fixture; limit_30 may use recorded SPY evidence with actual configured read-only limits. These controlled requests do not authorize orders, extra calls or new capabilities.

If a transformation beyond these listed constructions is needed, document it prospectively and hash it before either arm sees that case. It must preserve the frozen question's intended failure and cannot make a missing positive market capability look supported. If that cannot be done, retain not_assessable.

## Reporting and decision limits

Keep all 30 rows, with evidence class visible on each. Report real recorded-input and synthetic-failure outcomes separately as well as the overall denominator. Synthetic successes may establish controlled handling of a failure, but cannot be described as live-source accuracy, live freshness, real historical performance or proof that missing product metadata exists.

The original useful-answer scoring and paired-improvement requirements remain unchanged. Report the source class of every win/tie/loss, and do not summarize gains confined to synthetic failure cases as demonstrated improvement on actual market interpretation.

No source policy makes a mock model count as a real model. The real dispatch/accounting requirements and remaining daily allowance still apply. No provider/model call or allowance change is authorized here. Future failures cannot be removed from the denominator; further tuning after v2 answers are exposed retires the set for unseen claims.

## Verification

The companion hash record identifies this amendment and verifies that the original cases, rubric and manifest remained byte-for-byte unchanged during creation. A future runner must verify those hashes and the binding hash before executing either arm. This amendment is part of that prospective frozen protocol, not a retrospective rewrite of evaluation results.


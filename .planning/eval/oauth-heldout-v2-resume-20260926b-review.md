# Independent completed-run review

**Decision: incomplete; not accepted for release.** The candidate improved usefulness on this recorded comparison, but the frozen full-set acceptance conditions are not met.

The independent A/B scores were frozen before opening the arm key, candidate/baseline reports or durable usage audit. Blind score SHA256: 5e4b98bebe7d3315348533d1929cfaa5ba59bd24806ed8f03d2ba03c50f429d5. All 30 rows remain in the denominator; missing prerequisites receive no improvement credit. Extra explanation fields made arm style inferable, so this is identity-blinded review, not a claim of perfect blinding.

## Results

- Candidate usefulness: 67/90; deterministic baseline: 53/90. Missing prerequisite contributes zero to both totals.
- Paired results: 11 wins, 18 ties, 0 losses, 1 not assessable. Wins include explanation and multi-ticker families, with actual candidate dispatch and validated content.
- Grounded useful answers: candidate 26/30; baseline 20/30. Among the 29 assessable rows: 26/29 and 20/29. These are rubric scores, not trading-performance estimates.
- Execution: 28 completed saved answers without fallback, 1 saved safe input-size fallback, and 1 expected four-ticker route refusal. All 29 saved answers per arm passed the runner reload check. The candidate run correctly remains FAILED because its required three-ticker model interpretation was incomplete.
- Candidate dispatches: 25, with validated model content used on 25 rows. Baseline: 0. All three price-only cases and the four-ticker refusal made no recorded model dispatch. No model-output validation rejection is reported; the one failure occurred before dispatch because input was too large.
- No displayed critical grounding error or scope violation was identified. This is not a claim that the 30 cases independently prove every ownership, order, budget or retry invariant.

## Important incomplete cases

- explain_06: recorded IWM flow alerts or confirmed real-store absence were required. Inputs explicitly say the alert store was not supplied and cannot be read. This is not confirmed absence. Keep not_assessable, even though the displayed answer avoids invented profit odds.
- compare_11: all three tickers were shown safely, but the model input exceeded the bound, so no candidate interpretation was dispatched. The fallback gets no improvement credit. The later input-compaction change cannot be validated by these frozen old answers.
- explain_08: both arms give generic missing-volatility wording instead of precisely explaining which implied-move prerequisites are present versus absent. Both score 1.
- history_22: both arms withhold an unsupported change but fail to identify the supplied 166-versus-442-contract coverage mismatch. Both score 1.

## Evidence and visible answer review

Reviewed all original questions, prerequisites and answer criteria; applied the prospectively frozen source-policy amendment only to allowed recorded/synthetic failure contexts. The AAPL case uses its actual later captured source in the bound inputs; the older proposal still calls it unbound. This stale label is retained in the detailed source-class counts with the actual supplement stated, not treated as proof of missing AAPL data.

Compared blind answers to decoded completed reports: all captured blind fields match. Grading includes summary, sections, gaps, model explanations, model relationships, model sections and the current shared saved-chart rendering. This matters: summary/sections alone are identical, but additional model explanations are visible. Shared chart explanations earn equal credit in both arms; extra words alone earn none. Rendering source hashes are recorded in the blind grade artifact.

Independently recomputed quote/count/expiry/gamma profile and total values from hash-verified raw chains with Decimal arithmetic, plus raw map selected-cell, flip and saved-price checks. No mismatch was found. Original source times, requested tickers and saved screen identity were checked. Other derived level formulas were not independently reimplemented; this review does not replace their deterministic tests. Raw-evidence check details are retained separately.

Controlled synthetic cases are map_18, history_22 and source_24. They yielded no paired wins. All 11 wins are recorded Public inputs with controlled screen/history context. Artificial stale-map time proves controlled stale handling only, not that Public supplied that timestamp.

## Usage, timing and remaining gates

The separate durable-usage audit matches all 25 saved reservation/generation/token records to completed reservations and the live shared quota. This reviewer checked the audit file hash, candidate file hash and report consistency; the live store extraction itself was performed by the parent reviewer. Today records 25/40 calls; the earlier day still records 34. No reset or allowance change was made. All 25 application reservations are completed; this does not establish an upstream invoice or dollar charge.

Reported totals: 514,283 tokens, including 498,133 input and 16,150 output; 161,280 input tokens were cached. These are provider usage fields, not a dollar calculation. Dollar cost remains unknown; subscription allowance cannot satisfy the required monetary reconciliation or prove the original hard dollar gate.

Observed end-to-end case latency: median 13.2265 seconds, maximum 26.438 seconds, across all 30 cases including immediate refusal/fallback. Time to first progress was not measured because stored progress events have no timestamps. Per-case capability invocation totals are also not retained in the completed reports; do not infer them from configured limits.

Market-provider refresh requests were zero in the recorded-input run. This does not erase the separately captured original market-source acquisition requests. Application reservation count is not a claim to independently see every internal upstream transport attempt.

The exact plan section 5.4 and frozen rubric require a stronger-candidate comparison. None was run. The old description of this comparison as optional is incorrect. Full-set coverage, complete candidate execution, monetary evidence and the stronger comparison remain open. No trading edge, probability calibration, live-trading permission or full-plan completion is established.

The set has now been exposed. Any tuning after these results retires it for unseen acceptance claims. A future acceptance run needs a new independently frozen set; these results remain an immutable diagnostic comparison.

## Per-case frozen scores

| Case | Candidate | Baseline | Result |
|---|---:|---:|---|
| price_01 | 2 | 2 | tie |
| price_02 | 2 | 2 | tie |
| price_03 | 2 | 2 | tie |
| explain_04 | 3 | 1 | win |
| explain_05 | 3 | 2 | win |
| explain_06 | N/A | N/A | not_assessable |
| explain_07 | 2 | 1 | win |
| explain_08 | 1 | 1 | tie |
| compare_09 | 2 | 1 | win |
| compare_10 | 2 | 1 | win |
| compare_11 | 1 | 1 | tie |
| expiry_12 | 2 | 2 | tie |
| expiry_13 | 2 | 2 | tie |
| expiry_14 | 3 | 2 | win |
| expiry_15 | 2 | 2 | tie |
| map_16 | 3 | 3 | tie |
| map_17 | 3 | 3 | tie |
| map_18 | 2 | 2 | tie |
| map_19 | 3 | 3 | tie |
| history_20 | 3 | 2 | win |
| history_21 | 3 | 2 | win |
| history_22 | 1 | 1 | tie |
| source_23 | 3 | 1 | win |
| source_24 | 3 | 3 | tie |
| source_25 | 2 | 2 | tie |
| unsupported_26 | 3 | 2 | win |
| unsupported_27 | 2 | 2 | tie |
| unsupported_28 | 2 | 2 | tie |
| limit_29 | 2 | 2 | tie |
| limit_30 | 3 | 1 | win |

Every per-arm reason, abstention, source class, dispatch identity, saved-answer result, latency and usage record is in the decoded grade artifact. There are no paired losses to list.

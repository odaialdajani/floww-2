# Exposed development review - 2026-09-11

Reviewed oauth-development-20260911.json against the original case definitions and scoring rubric for OH1-13, OH1-15 and OH1-29. These cases were already exposed and the product was changed after earlier results. This is development evidence, not held-out acceptance, promotion approval or a trading-performance test.

## Paired scores

| Case | Baseline grounding | Candidate grounding | Baseline usefulness | Candidate usefulness | Abstention baseline / candidate | Result |
| --- | --- | --- | --- | --- | --- | --- |
| 13: QQQ gamma meaning | 2 | 2 | 1 | 2 | not_applicable / not_applicable | Candidate win |
| 15: IBM saved coverage | 2 | 2 | 1 | 2 | not_applicable / not_applicable | Candidate win |
| 29: IBM executable option entry | 2 | 2 | 1 | 2 | correct / correct | Candidate win |

All three cases are assessable. **3 wins, 0 ties, 0 losses out of 3 matched exposed cases.** No critical failure was found in either arm; all candidate dispatch checks pass. No transport failure, fallback, unassessable case or cost-limit result was dropped from this three-case denominator. The other 27 original cases were not rerun here.

- Case 13: the baseline gives scoped, degraded exposure values and says they do not establish direction, but does not explain the measure. The candidate adds the exact missing explanation: option delta sensitivity combined with open interest and assumed position signs, not observed dealer inventory or a directional prediction. It retains unknown chain time and stale price status.
- Case 15: the baseline supplies the actual 274 IBM contracts and September 11/18 expiry dates, but incompletely answers what coverage is not established. The candidate keeps those figures and explicitly distinguishes saved coverage from all listed contracts, all expiries and all market participants. It does not turn the requested all scope into complete-market coverage.
- Case 29: the baseline safely withholds an executable proposal, but gives broad missing-data sections. The candidate directly explains that the underlying price is not an option premium and that the exact contract's verified bid/ask are absent. No entry is invented and the stale underlying price remains stale.

The gains are question-specific explanations, not additional quantitative analysis or a broader capability. Extra relationships merely restate availability and do not independently earn usefulness credit.

## Evidence and usage

Programmatic comparison confirmed identical facts, snapshots and screen context between both arms in every case. Every selected explanation exactly regenerates from the current server menu; all explanation references resolve to the matching ticker and horizon. Original input hashes are preserved in the input artifact: case 13 starts bbd7fc19, case 15 ae7a0e5c, case 29 e94371ea. No new provider or model call was made during this review.

Three recorded app dispatches used gpt-5.6-terra, medium effort, standard speed. The call counter moved from 27 to 30 of 40. Reported usage totals 46,132 input tokens plus 1,084 output tokens, 47,216 total; per-case wall times were about 11.718, 10.266 and 9.297 seconds. OAuth dollar cost remains unknown subscription usage. These figures do not prove exact upstream attempts or a dollar budget.

## Earlier review fixes

Current source and the focused 20-test run close the three earlier findings: an extra stale historical price no longer invalidates an existing healthy compatible scalar price/flip pair; explanations print their group scope; and model-requested history replaces the corresponding What changed unavailable entry. The dedicated tests also reject incompatible observation times and preserve the validated change reference. Scoped source review found no new unknown-ID or unrestricted model-prose publication path.

Remaining limits: this tiny exposed sample cannot establish general improvement or unseen safety. The candidate selects server-authored explanations; broader causal analysis is still restricted. No new verified company, option-quote, executable trade or calibrated probability capability is demonstrated. Baseline answers still produce ten sections for the coverage and option-entry questions, leaving unnecessary content below the concise candidate explanation. The displayed map scope is technically explicit but a raw map hash would be less readable than a human scope label. Full unseen acceptance and live rendering remain separate work.

# Critical chain selection review - 2026-09-27

## Verdict

FIXED in owned source; root must independently review and commit. The actual mounted chain table ignored expiry, minimum open interest, moneyness, maximum days, and sorting on its preferred public response. This could make a trader believe a chosen expiry or liquidity filter was active while unrelated contracts remained visible.

## Reproduction before changes

Mounted actual OptionsChainTable with three synthetic call contracts, strikes 110/90/100, mixed 2026-10-02 and 2026-10-30 expiries, open interest 200/500/300, days 1/30/7, and spot 100. Changed each control independently. All five controls triggered another fetch with only ticker and signal; each left the original rows [110,90,100] untouched. Five intentional assertions failed against actual displayed cells. The initial fixture carried moneyness_pct with the opposite sign from the fallback convention, but the moneyness expectation derives from the actual call strike and spot, so the failure remains valid. Durable regression fixtures use the correct fallback sign.

A second red run executes all 22 durable new regression cases against a temporary copy of the original committed component, with import paths alone rewritten to resolve from the temporary folder. All 22 fail; most filter cases stop at the already incorrect default ascending sort, so the first five independent control reproductions are the direct evidence for each selection defect.

## Source findings and correction

- Preferred request discarded all constructed filter parameters. Local selection previously only filtered call/put side.
- Actual merged route backend/routes/market_data.py returns rows/count/dte, whereas the old adapter consumed contracts/n_contracts/T and erased every fallback row. Adapter now accepts both real response shapes.
- Fetch is now tied only to ticker. Both sources are filtered and sorted locally with the same semantics; changing a control no longer triggers an unchanged network fetch.
- Expiry uses exact date, minimum open interest is inclusive, maximum days is inclusive and preserves the fallback's supplied day value. Missing values do not satisfy active numerical filters.
- Backend routes define no moneyness or sort behavior. ITM/OTM now use call/put intrinsic direction against response spot. ATM is explicitly labeled within 1% of spot; this uses the existing table near-spot band rather than an undisclosed rule.
- Missing numeric readings remain unavailable instead of being converted to zero; unknown contract side remains unknown instead of put. Sorting places unavailable values last in either direction.
- Loaded rows are tagged with the requested ticker and hidden immediately when the prop changes. Cleanup ownership prevents late successes replacing new data and late failures launching an obsolete fallback. Both-source failure is visibly reported.
- No chain research context was added. Root owns research publisher lifetime changes.

## Verification

34 passed, 0 failed across existing OptionsChainTable.test.jsx and new OptionsChainTable.filters.test.jsx. New suite: 24 mounted checks covering eight selections against each source, put/call moneyness with combined filters, current ticker switching and late response rejection, obsolete fallback avoidance, missing values/sort order, unavailable open interest/days, error state, expiry reset between symbols, and response-spot highlighting. Existing smoke tests produce preexisting React act warnings; new suite does not. git diff --check passed (only Git line-ending notice).

Proof: .planning/eval/critical-chain-selection-proof-20260927.json includes original visible cells, requested argument keys, red/green test outcomes and current source hashes. Raw temporary scripts, outputs and configurations: C:/Users/DARK HERO/AppData/Local/Temp/floww-chain-review-e25801c5. Processes launched hidden and exited.

## Limits

Synthetic transport responses, actual mounted component, no real provider/model call or app restart. No full App mount, browser painting, CSV download, or whole-market expiry completeness acceptance. Filters cover the returned chain only. No other production files edited and no commit performed by reviewer.

## Final independent-review siblings

Root identified retained expiry and mismatched spot highlighting. Two mounted regressions failed before the final correction. Ticker changes now reset expiry to All Expiries; near-spot highlights use the same chain-response spot used by the filters. Final source edit was 2026-09-27 02:18:03 UTC. Final 34 tests pass. Root must rerun any build started before that time.

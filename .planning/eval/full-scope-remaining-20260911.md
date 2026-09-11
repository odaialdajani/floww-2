# Full requested scope and remaining work

Updated 2026-09-11 23:17 UTC. The user's 22:32 instruction retains the original full objective: preserve local work, reconcile shared work, review incoming changes and outstanding PRs, implement both exact AI/UI plans, report genuine blocks and all unfinished work. Mobile optimization is set aside. Neither full-plan completion nor complete audit of every incoming line is claimed.

## Completed and newly corrected

- Preserved the original working tree in an external safety copy and commits; merged current shared main with reviewed conflict resolutions. PRs 3/4/5 were reviewed, with obsolete/broken branches left unmerged and useful source-time fixes retained. No remote messages, push or deployment.
- Production desktop redesign and shared research are implemented. Actual Public market data, local persistent research storage and managed ChatGPT login were exercised on both dashboards. Missing/stale inputs remain labeled.
- Restored settings preservation and on-demand outcome access; outcome calculation explicitly refuses the retired data source in Public-only mode. Restored chart selection across same-scope refresh, exact small readings and saved chart explanations.
- Corrected incoming order transport, disabled-order handling, confirmed fill quantity/price, symbol/side accounting and nonfinite inputs. Separate broker orders now retain distinct journal identities; old records and close keys are preserved. Newer saved closes refresh cached broker execution without losing local notes. No actual broker/order or production-journal migration was performed in these checks.
- Failed ingestion writes now have explicit unconfirmed-row accounting; later independent batches still run and normal shutdown awaits active writes. No blind retry or exactly-once claim.
- Restored meaningful formerly skipped checks with isolated dependencies and fixtures. One restored original assertion exposes a real missing daily-checklist contract; it remains a failure.
- Fresh 30-question comparison now has frozen sources, independently checked derived inputs, controlled clocks/history, actual isolated storage, route admission/reload checks and a sealed executable. All 30 input checks pass with zero candidate calls. Earlier failed checks and the unsuccessful original comparison remain preserved.

## Unfinished work and its dependency

| Work | Current state | Required next step |
| --- | --- | --- |
| Fresh AI answer usefulness | First independent comparison failed; three later exposed development improvements are not fresh acceptance. New 30-case set is ready but unrun. | One candidate requires 26 model calls, then independent grading for correctness, usefulness, omissions, usage and latency. Daily limit remains 40; 34 were reserved after the final real desktop question. User was asked to permit 26 additional calls; no answer has been received as of this update. Otherwise wait for a new UTC day. |
| Complete company, microstructure, comparison and historical research | Initial cache-based exposure, levels and explicit unavailable states are implemented; broader catalog remains incomplete. Realized-volatility reader has no production history callback. | Accept the initial research release, then supply verified source capabilities, coherent historical bars/product-expiry metadata, meaningful inputs and corresponding acceptance checks. Do not advertise placeholders. |
| Concrete trade proposals | Not complete. | Accepted research/catalog, supported strategy shapes, current executable quotes and explicit refusal for unsupported legs. |
| Paper account and lifecycle | Venue comparison and accounting proposal prepared; full durable paper lifecycle not complete. | User decision on counting slippage once, then accepted research/proposals, order/fill/cancel/restart/expiry/exercise proofs and human-confirmed paper acceptance. The existing accepted accounting decision has not been silently changed. |
| Watches, briefs and forward learning | Not complete. | Accepted research, private delivery controls, meaningful forward observations and outcome/learning checks. |
| Live trading | Not enabled by this implementation. | Separate written authorization, concrete risk boundaries, future paper/forward evidence and human confirmation. Read-only Public access is not order authorization. |
| Morning checklist | Restored original test fails: response provides regime but omits levels, strategy, risk and hedging fields used by retained desktop consumers. Same omission exists in both merge parents. | Choose truthful replacement behavior before wiring legacy helpers that suggest trades/risk percentages. No placeholder objects, skipped assertion or automatic revival of those suggestions. This is an unresolved code requirement, not an external outage. |
| Eventual broker-entry reconciliation | Immediate confirmed fills are correctly recorded; changed later quantities require reconciliation. | Durable pending-entry tracking and evidence-backed later fills. Historical guessed holdings require broker proof before repair; no automatic deletion or rewrite. |
| Missing model/reference artifacts | Tests depending on absent files remain unverified. | Supply their exact artifacts or formally retire their claims. Passing unrelated tests cannot replace this evidence. |
| Complete incoming-code audit | Conflict, PR, desktop retention, Public scan, ingestion, order boundary and journal reviews performed; whole tests run. | Do not equate these bounded reviews with a line-by-line audit of all 133 changed production files. Any expanded audit needs its own bounded inventory and evidence. |
| Mobile optimization | Explicitly paused by the user. | No work scheduled; completed fixes retained. |

## Evidence limits

The final real Solstice check selected SPY strike 764 / expiry 2026-09-14, retained it across refresh, saved a real model-assisted answer with 16 facts and reloaded it through Saved answers. The displayed +48.06M cell value, whole-chart flip and stale/unknown-source limits remained unchanged. Evidence: `public-solstice-selected-real-20260911-2316.json`; inspected desktop screenshots remain local under output/playwright. This was one development/acceptance interaction within the unchanged daily cap, not part of the fresh comparison.

The preview backend was started at21:44; it verifies the unchanged research path and freshly built frontend. Later outcome/order/ingestion changes were verified through isolated production routes and stores, not by claiming that old preview process loaded newer modules. No mobile tests were added after the pause.

Final frontend:84 suites/723 tests passed; production build succeeded. A controlled journal browser exposed equity profit incorrectly scaled100times; red regression then shared math correction gives+2 for2 shares500->501, preserves fractional shares and standard-option sizing. Viewed final desktop confirms the closed row and preserved note. Equity type selection was added after full frontend test collection; final build/browser include it.

Final whole-backend run:5656 passed,2 failed,39 skipped,0 deselected,0 errors;68.08% coverage in472.69s. One failed test retained an obsolete empty-expiry coverage expectation. It now asserts only usable returned dates and that both broker-listed dates were actually requested;19 related checks pass after that test-only correction. The daily-checklist failure remains unresolved. No production backend source changed after the full run; no new full-suite pass is claimed. Full Ruff, required-medium Bandit, whitespace and outside-network guard passed. See `backend-suite-20260911-2324.json` and `delivery-checks-20260911-2324.json`.

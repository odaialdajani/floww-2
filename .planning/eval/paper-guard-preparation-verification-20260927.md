# Guarded paper preparation verification

Verified 2026-09-27 UTC. This is a bounded unmounted preparation slice for new isolated accounts. No application restart, real account change, provider/model call, paper activation or live order occurred. Exact four-file identities: paper-guard-source-manifest-20260927.json. All match the independent review identities.

## Implemented and checked

A durable funded assessment intent precedes valuation/risk evaluation. It captures the command and compact actual book basis without recursive guard data. Normal immutable account events save intent and resolution. A complete exact actual observation is required to resolve; incomplete/missing readings retain the fence. Passing economic candidates are independently recomputed from the saved command and source frame. Entry/reducing roles and held structure must match. Control changes precede final saved observation binding.

Guard credits are reserved alongside existing execution obligations. Two credits fund a bounded entry assessment; each held structure receives a finite budget for reducing assessments. This adds storage liabilities, not money. It deliberately reduces usable account capacity. A full ordinary event budget still allows the tested funded refusal and close. Failed/capacity-limited resolution retains the intent. New entry is blocked while any intent remains unresolved. Old overlapping assessments are not silently rebased after later account changes.

Guarded accounts use separate collections, require explicitly new empty state, and cannot be found through unchanged legacy paper services. No migration occurs. Passing decisions apply their own exact time bounds within the conditional server update, rounded inward to milliseconds. Caller bounds cannot broaden them. This proves server expression evaluation time, not final acknowledgement time.

## Executed evidence

- 74 pure paper checks passed, including 8 new guard regressions plus all prior 66 arithmetic/execution/valuation/risk cases. Full verbose result remains at output/paper-guard-all-tests-20260927.json. Invocation: backend/.venv/Scripts/python.exe -m unittest discover -s tests -p test_agent_paper_*.py -v.
- Ruff passed on the exact four source/test files after the final review.
- Eight actual isolated-store checks passed in the final expanded verifier: collection isolation; refused actual equity/peak1188.70 at full ordinary capacity; protected close stage/fill cash633.05 with that peak retained; exact fresh-process state and event recovery/projection; injected prewrite failure and checkpoint/frozen restore; distinct begin race; insufficient new-position capacity with funded observation-only resolution; expired/future/current server predicates.
- Independent review replayed the original six store checks in another fresh isolated account, plus four further actual-store checks: distinct same-version begins produce one winner, winner blocks new entry, twelve duplicate retries consume no extra credits, successful write with lost reply retains intent and same-identity reconciliation does not repeat it.
- Independent review found three finalizer linkage defects during preparation. Missing actual readings, buys under a reducing intent, and passing candidates built from different prices are now refused. Adversarial rechecks and exact source hashes are recorded in paper-guard-preparation-review-20260927.md.
- Sanitized final-store and independent race proof: paper-guard-store-proof-20260927.json. Reproduce the expanded store proof from backend with its Python: -m scripts.verify_paper_guard --run --report <new report path>. It requires a fresh report/checkpoint/restart set and a new prefixed synthetic local test account; existing artifacts are never overwritten. Test records remain for inspection.

## Boundaries and unfinished work

1. No real action controller composes this mechanism, authenticates owner acceptance, or obtains verified proposal/product/price/session/account sources. The low-level repository is a trusted internal persistence primitive, not an authorization endpoint.
2. Replenishment requires exact event projection verified by a future trusted caller. The finite credit budget does not guarantee unlimited exit attempts. Old overlapping intents require historical reconstruction against their captured book; that reconciliation is not implemented. Frozen restore preserves uncertainty and does not authorize new trading.
3. Stable begin/resolution identities and request recovery must be composed at the controller level. Lost-BEGIN-response proof does not establish every resolution crash schedule. A timeout must never be treated as a refusal or replayed as a fresh financial operation.
4. Full account/risk choices remain unanswered. No balance, trade loss, daily loss, drawdown or exposure settings were assumed. Explicit risk formula semantics remain subject to owner choice. Peaks are sampled observed highs, not all unobserved intraday extrema.
5. Actual option expiry/exercise/settlement/deliverables and share corporate actions/dividends remain unsupported. Unknown lifecycle retains holdings. Product admission stays disabled. Earlier research evaluation, approved models/cost controls and human confirmation gates still apply. Live trading remains separately unapproved; mobile remains paused.
6. Server-expression bounds do not prove final journal acknowledgement-time freshness, every retry/lock-wait schedule, arbitrary byte saturation or provider source truth. These remain explicit limits.

This advances the durable-refusal preparation item in paper-risk-preparation-verification-20260927.md but does not supersede its mandatory production-composition gates or claim the full project complete.

Reference semantics used: MongoDB system NOW variable is stable across the operation (https://www.mongodb.com/docs/manual/reference/aggregation-variables/); query expressions use $expr (https://www.mongodb.com/docs/manual/reference/operator/query/expr/).

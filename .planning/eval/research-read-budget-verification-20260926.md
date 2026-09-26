# Shared research read allowance - 2026-09-26

The active ResearchService now reserves each capability/ticker invocation before dispatch and refuses the ninth. This closes the unbounded 9/10-entry history reproduction in [original review](research-read-budget-review-20260926.md); it is not new held-out model acceptance or completion of the AI plan.

## Count contract

One context cache read counts once. Stored flow, selected-map access, optional daily-bar read, grouped structure calculations, grouped volatility calculations and owned saved-history comparison each count once when requested for a ticker. Related structure outputs share a single calculation from the frozen context. A history capability's internal turn/anchor queries are not falsely counted as two capabilities. These are capability admissions and actual entries; they do not claim actual provider request or model dispatch counts. Source acquisition remains cache-only here.

A simple price lookup retains one context read. Three-ticker pure history uses three contexts plus three history comparisons. A clearly requested three-ticker structure comparison uses three contexts plus three grouped calculations. Single-ticker general questions retain the full prior evidence set, avoiding lexical suppression of implied/expected moves. Broader requests can return explicit partial coverage under eight admissions; denied capability/ticker work is recorded and shown in gaps. Unsupported domains are not silently implemented by this routing.

Durable activity distinguishes reserved from actually started attempts, completion, errors, timeouts, worker-capacity refusal and denied work. A failed reservation save enters no callback. Entered failures/timeouts are not refunded. The activity is saved with completed, failed, cancelled and interrupted results; pre-start cancellation saves zero entries. Startup recovery preserves uncertain old reservations as interrupted_unknown, with entry_count_complete false, rather than inventing execution or refunding them. Owner-scoped replay preserves the saved record.

Synchronous cache/read/calculation callbacks use a shared four-worker pool. Waits use the smaller of five seconds and remaining monotonic turn time. Cancellation does not kill an already-running thread: its charge remains, the worker slot remains occupied until exit, late results cannot change terminal records, and unresolved work is marked. A frozen question cannot start a later model call. A failed cancellation save stops its task; it does not publish a partial answer as completed. No new owner can freeze another owner's budget. Identical initial/follow-up history uses a copied memoized result, including unavailable/error outcomes, rather than retrying the same unavailable read. Different history comparison modes have separate identities.

## Evidence and limits

- 275 research tests passed under the outbound-network guard, including 27 new allowance/cancellation/ownership/saving tests; 27 existing warnings remain. No skips in this run.
- 72 related agent-hub and Solstice integration tests passed under the same guard.
- Ruff passed for all changed source and tests.
- Two separate Python processes saved/reopened actual local MongoDB records: completed six-read result unchanged, different owner refused, unfinished saved admission recovered as interrupted with unknown entry status. This is process/client reopening, not a database-process crash/restore certificate.
- Independent adversarial review found a cross-owner cancellation regression and missing multi-intent evidence during development. Both were reproduced and repaired before commit; see [repair review](research-read-budget-repair-review-20260926.md). Later root tests also reproduced and repaired failed-cancel-save completion and missing pre-start zero-count records.
- The prior 5,946-pass full backend run applies to the preceding market/history cohort. This repair was verified with the focused research and related runs above; do not relabel that earlier full run as covering later edits.

The source hashes and result summary are in [verification manifest](research-read-budget-verification-20260926.json). Detailed logs/probes remain local in output. No live provider/model calls, quota reset, USD-cost acceptance, live orders or deployment occurred. Maintenance uses its own bounded read scope and is not a user-turn count. Older saved turns without activity remain unknown; no backfilled counts are fabricated. Fresh evaluation still needs a new independently frozen question set, actual alert evidence, stronger-model comparison, distinct actual model/provider counters and honest client-visible progress timing.

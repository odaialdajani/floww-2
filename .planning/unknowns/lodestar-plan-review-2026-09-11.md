# Lodestar plan review record

Date: 2026-09-11.
Scope: reconsider and revise the agentic AI implementation plan from the user's Claude Code session, preserving the product goals. No application implementation, broker calls, market-data requests or paid model calls were performed.

Canonical revised plan: `C:/Users/DARK HERO/.claude/plans/i-would-like-to-replicated-stardust.md`.
Preserved original: `C:/Users/DARK HERO/.claude/plans/i-would-like-to-replicated-stardust.v3-before-review-2026-09-11.md`.
Original SHA256: `619c022d038d230d7dc60eeb5df341405d7a5af895ed59f0eb072e2b9c54c0aa`.
Code baseline: HEAD `1a512c335757cc0dbccb35fd7e0a2bc728568498` plus existing uncommitted work. Review conclusions apply to the inspected working tree, not an assertion that all changes were committed or deployed.

## Review method

The original plan, actual agent implementation, shared integration points, project constraints and accepted decisions were read. Three independent reviewers covered data/tools, UI/storage, and trading/outcomes. Each then challenged the revised draft. The parent incorporated their material corrections and reread the complete document. A narrow closure check confirmed all seven final storage/identity corrections were resolved.

Primary provider references were checked for structured model output, tool calling, routing/caching/cost accounting, Mongo atomicity/driver lifecycle, exchange calendars, and Public/Alpaca capabilities. Links and time-sensitive limits are recorded in the plan. Undocumented account limits and a Public sandbox were not inferred.

## Material changes and disposition

| Finding | Revision |
| --- | --- |
| Most registered tools were empty stand-ins | Small meaningful capability set first; explicit adapters, positive-output fixtures, full expansion gated per capability |
| Model lacked actual values; agreement inputs were zero | Actual typed facts and initial deterministic reading precede model inquiry; recompute after added evidence |
| Generic wrappers guessed incompatible arguments | Exact per-calculator adapters and numerical equality cases |
| Repeated chain fetches and inaccurate quota units | Immutable shared snapshots, coordinated cold reads, actual request-fanout reservations |
| Expiry/calendar/Greek provenance errors | Exact horizons, fractional expiry, product cutoffs, unknown observation times and per-field provenance |
| Custom sentence syntax added fragile complexity | Validated structured answer, typed relationships, progress events plus one persisted final result |
| Async storage was not actually connected | Injected asynchronous repository and conditional final persistence |
| Different IDs, global request reuse and reconnect-triggered work | One owner-scoped identity, bounded idempotency lifetime, observers separated from jobs |
| Cancellation/claim/replay race | Terminal state, answer, evidence, claim seed and final cursor committed atomically |
| Local sessions could lose ownership or expose accounts | Durable owner, cookie rotation/recovery, scoped credentialed CORS, proxy gate and separately authorized account binding |
| Spend was estimated after work and could reset | Atomic pre-reservation, actual usage reconciliation, explicit day rollover and uncertain-call accounting |
| Missing chart context and final answer/evidence wiring | One shared screen/conversation state; real tests in both tabs |
| Claim grading started too late and lacked sufficient paths | Minimal resolver/path collection in first release, missing/ambiguous outcomes retained |
| Direction hit rate was treated as execution proof | Separate prediction, trigger, fill and after-fee evaluation; independent-session baselines and no automatic promotion |
| Option helper assumptions were overstated | Independent proposal economics, premium-factor/deliverable distinction, verified lifecycle before entry |
| Existing accounting decision conflicted with cash math | Clarifying/superseding decision is a paper milestone prerequisite; accepted decision not edited |
| Order retries and cap checks could race | Atomic risk check plus reservation, stable intent, uncertain-submission reconciliation and final enablement recheck |
| Old calendar estimate overstated certainty | Withdraw total-day commitment; estimate milestone effort after evidence and separate forward-observation time |
| Full-scope features could disappear into broad labels | Explicit retained model/portfolio/Kelly/strategy-quote/notes/preferences deliverables |
| Research exit could accidentally depend on future trading tests | Research checks gate the first release; paper/live checks gate their later milestones |

## Observed offline evidence

An isolated in-memory probe imported the actual catalog, called its placeholder, then substituted all data functions and model generation to inspect the actual turn logic without network or a real database. Opposite fixture values were supplied in separate turns.

```text
registered tools: 65
tools returning only ticker/horizon: 52
actual placeholder result: {"ticker": "SPY", "horizon": "0dte"}

input reading: 3471.23
returned deterministic score: 0.0
returned direction: neutral
model prompt contains supplied reading: false
model prompt contains supplied spot: false

input reading: -3471.23
returned deterministic score: 0.0
returned direction: neutral
model prompt contains supplied reading: false
model prompt contains supplied spot: false

collections written by each substituted turn:
agent_turns: events, horizon, ticker, turn_id, verdict
agent_structure_snapshots: ledger_hash, ticker, ts
agent_claims: no write
```

This proves defects in the existing turn integration under controlled inputs, not the quality of a real model or live feed. The plan treats them as implementation blockers rather than claiming they were fixed.

## Document verification and remaining limits

The completed draft was checked for ordered sections 1 through 14, balanced code fences, ASCII diagrams/text, required correction clauses, valid link formatting, and intact original/backup hashes. The original was checked again before replacement; final copy equality is verified at delivery.

No full application test suite, frontend rendering, paid model evaluation, actual trading performance or deployment was certified. All implementation gates remain pending. Remaining account policies, model/provider selection and forward-performance criteria have explicit decision points before the affected feature is enabled. These are planned implementation decisions, not unresolved permission requests for this document revision.

The previous version remains available for comparison. No accepted architecture decision, app source, project status or kanban card was changed by this review.

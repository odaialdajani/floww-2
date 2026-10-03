# FLOWW commissioning review — disarmed

Contract: `floww-integration.v1`; research draft `trade-plan-draft.v1`; private operator report `native-handoff.v1`. This is an implementation/review packet, NOT approval to activate capture, models, native workflows, backend entry, deployment or real-money trading. No account credentials belong in this document or a frontend tool.

## Policy to approve only after producer acceptance

| Required policy | Production value | Acceptance required |
|---|---|---|
| Exact Public account ID / account type | **UNSET** | Authenticated account read; product entitlement, funding and permission verified for this account. |
| Execution owner | **UNSET** | Exactly `PUBLIC_NATIVE_AGENT` or `FLOWW_BACKEND`; current workflow/position/order inventory, including workflows created outside FLOWW. |
| Allowed symbols / products / expiries | **UNSET** | Listed exact OSI/series/expiry/multiplier; SPX entitlement is not inferred from SPY. No synthetic listing or expired contract. |
| Premium budget per entry | **UNSET** | Server-enforced premium/fee/slippage-aware bound, not an example NRG/KTOS budget. |
| Daily loss / aggregate exposure limits | **UNSET** | Durable account-policy enforcement with actual fills, fees and current positions. |
| Maximum concurrent positions | **UNSET** | Includes native and unknown/open backend ownership. Unknown inventory refuses entry. |
| Cash versus margin | **UNSET** | Explicit account-compatible choice; no inherited broker default. |
| Price confirmation policy / evidence | **UNSET** | Dated, owning price-path confirmation, not adjusted sign, conviction or model prose. |
| Quote-age limit / liquidity / tick policy | **UNSET** | Current separate bid/ask clocks, uncrossed book, exact increments and multiplier provenance. Recorded quotes are research only. |
| Entry / near-expiry cutoffs | **UNSET** | Exchange calendar, holidays, early closes, DST, assignment/exercise exposure and supported product rules. |
| Protective behavior / risk exits | **UNSET** | Supported broker-native protection, actual eligible quantity and verification; a stop is not a guaranteed loss ceiling. |
| Authenticated approval scope / lifetime | **UNSET** | Server-stored approval binds immutable intent, context, account, policy, operator, scope and validity. UI booleans and reported workflow status never authorize entry. |
| Rollback operator / escalation contact | **UNSET** | Explicit responsible operator; no automatic re-arming after restart or policy expiry. |

Requested new-entry pause: **11:30–14:00 America/New_York**. This concerns NEW ENTRIES only. Protective exits, authenticated cancellation and reconciliation must remain available. A copied instruction or notification reminder does not enforce this rule. Public's native workflow must be reviewed independently in Public; FLOWW cannot control a workflow created elsewhere through a local lease.

## Current functioning disarmed path

1. Select an owning Solstice/Triad record, raw wall/dated scope/basis and exact contract. Missing quotes/Greeks/activity or same-session admission remain unavailable. The TideHunter bridge explicitly resolves a NEW separate owning record; Pro ckey/premium/conviction never become executable facts.
2. Ask bounded Lodestar research. The saved answer carries a deterministic, non-executable typed draft and evidence/observation references. Any changed selection invalidates the current-answer/brief grounding. An old history answer is not current permission.
3. In **AI choices**, load the authenticated provider catalog, choose **Use GPT-6.1-Sol · Extra high**, then explicitly **Save AI choice**. Catalog ID/effort support is verified; no operator preference was changed and no paid product turn was performed by this lane. A successful real turn must supply the actual `lodestar-trace.v1` effective settings; requested settings alone are not proof.
4. Explicitly choose an execution owner. Native ownership prepares an editable dated brief with all unsupplied policy values UNSET. Clipboard success means copied only. `/api/agent/handoffs` saves a private authenticated operator report against the owning completed research draft; delivery, broker verification and activation remain unverified. Reports are visible in Broker/Journal through private history.
5. `FLOWW_BACKEND` entry stays unavailable in this UI. Existing Alpaca Quick Trade remains **PAPER**; Public quote provenance does not relabel it. Existing authenticated Public cancellation remains reachable through its mounted server route; this increment neither removes that route nor submits a cancellation.

## Engineering blockers before any commissioning approval

Spark PR94 at observed `1fdf403d878378eb2d4c42d517071fe9559186b7` is a review candidate, not a commissioned executor. Its pure lifecycle is unmounted. Code review found in-memory intent/native/preflight state, caller-supplied approval identity, opt-in approval/preflight checks, missing budget/daily-loss/exposure/max-position enforcement, and a dict-versus-`Order` adapter mismatch. Restart reconciliation cannot recover records that were never persisted. The price fetch seam substitutes fetch time for absent vendor time. These are **producer engineering gaps**, not missing operator authorization; Zed does not edit Spark-owned files to hide them.

Required Spark follow-up: durable immutable intents/approvals/ownership and recovery; authenticated/default-deny dispatch admission; actual-adapter payload/receipt contract tests; account risk enforcement; missing clock refusal; restart-proven capture/price paths; admitted session inventory and bounded 14–60DTE query support. The current heatmap endpoint caps cumulative DTE at 30 and admits no lower-bound range; the UI explains that 14–60DTE is unavailable rather than guessing it.

Zero durable admitted live records remain the documented operational census. Backend-generated synthetic display and throwaway restart fixtures establish engineering behavior only. Underlying barrier/outcome labels are not realized option P&L or evidence of profitability.

## Rollback / resume review checklist — not executed

- Keep new entries and all new workers disarmed while validating the candidate. Do not change flags or restart existing services as part of this review.
- Before any later authorized activation, snapshot policy/intent identities and reconcile all open/unknown broker orders by original order ID; resolve remote native overlap first.
- On rollback, disable NEW entry admission and new capture/price-path work through the approved server controls; retain protective exits, reconciliation, authenticated cancellation and audit history. Do not delete unknown orders or mint fresh identities to retry ambiguous dispatch.
- Stop/pause a native workflow in Public itself and verify its state there; a locally saved `reported_paused` report is not proof. Never silently re-arm a disarmed/expired policy.
- Preserve frozen ML artifacts, protected TideHunter files, original worktrees and existing venue gates. No retraining, gate removal, merge or deployment is authorized by this packet.

Final operator decisions are deliberately deferred until the independent engineering and exact combined-head gates are reviewable. This document supplies no production budget or trading authorization.

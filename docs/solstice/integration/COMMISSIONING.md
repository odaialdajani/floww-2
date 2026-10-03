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

## Engineering acceptance versus commissioning

Initial verified merged main was `08f3793c242d943ab3b61b84e5394ce4602daa0a` (PR96/97/98); Spark merged PR99 during this pass to `aea1ed95ad02fe43a06df6a81fb7cf91e6079242`. [R16_ACCEPTANCE](R16_ACCEPTANCE.md) records the tested combined CODE e5ee1404 and its green local/hosted gates, plus preserved later source-equivalent receipt corrections. The old API-doc drift HOLD is closed by Spark's authorized generated-doc update; 376 paths verify. The old executor review is superseded in part: registered-store intent persistence/recovery, `Order`/dict receipt adaptation, terminal cancel/write-failure handling, OPEN-only pause and missing vendor-clock refusal are implemented. They are not repeated as missing work. The price producer is wired default-OFF; this review starts no worker or service.

`public_execution_lifecycle.py` remains an **unmounted injected service**, not the mounted Public route's authenticated executor. `submit(armed=False)` refuses by default, but `require_approval` and `require_fresh_preflight` still default false. `create_approval`/`verify_approval` validate supplied fields, not an authenticated server-side approval record. Supplied optional `risk_limits` check quantity/notional/process-local open-intent count; this does not establish account-wide daily-loss/exposure/position enforcement or verified remote native ownership. No Zed UI dispatch is wired to it. Existing venue-gated Public submission/cancellation remains separate and unchanged.

Spark [PR99](https://github.com/odaialdajani/floww-2/pull/99), frozen review head `c16e7f688ffd3f3150e2be67504c70c77702b2aa`, adds advisory stored-intent lookup, affordability, fill/remaining reporting and `intent-draft.v1`. Those advisory drafts are **not** authenticated approvals and are distinct from Lodestar's non-executable `trade-plan-draft.v1`. Source-head checks and combined-head checks are recorded separately. PR99 is now merged by Spark; Zed did not merge it. No candidate is merged by Zed automatically. The affordability comparison skips absent buying power or budget; it is not a default-deny account-policy admission. Its cross-process test uses sequential file-backed connections and a registry wipe in one process, not simultaneous process exclusion.

Remaining **producer engineering** before backend execution commissioning: accepted authenticated/default-deny immutable-intent/preflight/approval integration; durable account-wide policy and native/open/unknown inventory; genuinely atomic ownership where deployment permits more than one writer; truthful protection/recovery admission. Spark must propose any route/shared-schema boundary and obtain acknowledgment before a new broker-reachable path. Operator policy values alone cannot close these implementation requirements.

Remaining **replay/scope engineering**: the manifest accepts a chosen date but does not enumerate stored session dates. `/attribute/{ticker}` selects the last two ticker/day rows without checking source/scope/model/population compatibility; its `status=ok` is not a comparability admission receipt. Request an admitted comparable-pair/refusal contract and dated session inventory from Spark. Do not commission replay until admitted production records survive restart.

Expiry truth has two layers: routes `/heatmap/{ticker}`, `/trinity` and the Solstice snapshot/evidence surface validate the optional DTE query at `le=30`; the unfiltered chain loader selects by **expiry count**, drops expired dates and may include later than30DTE. This is not a global30DTE cap on returned columns. No explicit admitted14–60 lower/upper query exists. The UI keeps that range unavailable; Spark owns query/producer support, and the commissioning policy separately owns which admitted expiries may be traded.

Zero durable admitted live records remain the documented operational census. Backend-generated synthetic display and throwaway restart fixtures establish engineering behavior only. Underlying barrier/outcome labels are not realized option P&L or evidence of profitability.

## Rollback / resume review checklist — not executed

- Keep new entries and all new workers disarmed while validating the candidate. Do not change flags or restart existing services as part of this review.
- Before any later authorized activation, snapshot policy/intent identities and reconcile all open/unknown broker orders by original order ID; resolve remote native overlap first.
- On rollback, disable NEW entry admission and new capture/price-path work through the approved server controls; retain protective exits, reconciliation, authenticated cancellation and audit history. Do not delete unknown orders or mint fresh identities to retry ambiguous dispatch.
- Stop/pause a native workflow in Public itself and verify its state there; a locally saved `reported_paused` report is not proof. Never silently re-arm a disarmed/expired policy.
- Preserve frozen ML artifacts, protected TideHunter files, original worktrees and existing venue gates. No retraining, gate removal, merge or deployment is authorized by this packet.

Final operator decisions are deliberately deferred until the independent engineering and exact combined-head gates are reviewable. This document supplies no production budget or trading authorization.

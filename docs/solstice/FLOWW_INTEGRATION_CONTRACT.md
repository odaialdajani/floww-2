# FLOWW consumer integration contract — floww-integration.v1

Authority: 2 October 2026 `FLOWW-Shared-Integration-Contract.md` and `Solstice-Triad-Implementation-Contract.md`. Zed writes this consumer/interface document; Spark owns Public/recorder producers. Additive consumer contract only: no new route or shared schema is asserted to exist.

## Preserved boundaries

Route IDs: `heatseeker`, `trinity`, `skylit`, `flowseeker-pro`, `steal-three`, `portfolio`, `journal`, `public`; navigation derives from `frontend/src/shell/navConfig.js`. Preserve unrelated URL query/hash state. Workspace controls and map controls are separate.

Canonical observation/selection stays in `useScreenContext`, with its owner-token release guard. Research requests freeze that context. Old answers remain saved history, but must be labeled outside the current selection when any grounded identity changes. No selection change auto-invokes a model.

Existing metric/record contracts: `solstice-metric-contract.v1`, `metric-record.v1`, `gex.v2`, `recorder-health.v1`, `outcome.v1`, `research_barriers.v1`. Retain S² display-GEX and frozen S¹ feature-GEX. Actual recorded units, source clocks, axes, populations, gaps and exact contract identity must survive projection. No preview arithmetic or today's quotes in replay.

## Existing routes vs requested producers

Existing research catalog/preferences/session/history routes are consumed under authenticated `/api/agent/*`; provider catalog IDs are authoritative. `gpt-5.6-terra/medium` is historical product default, not evidence that requested GPT-6.1-Sol/xhigh is available.

Existing Quick Trade is Alpaca PAPER; Public quotes are data provenance, not execution venue. Public live submission has its own server gate. Do not weaken or relabel either path.

Spark's PR96/97/98 fixes are merged at verified main `08f3793c242d943ab3b61b84e5394ce4602daa0a`; generated API docs include376 paths. The old PR94 review is historical, not the current producer checklist. PR99 runtime head `c16e7f688ffd3f3150e2be67504c70c77702b2aa` supplies advisory lifecycle/draft improvements; later doc corrections and PR99 are now merged by Spark at current main `aea1ed95ad02fe43a06df6a81fb7cf91e6079242`. Tested combined CODE e5ee1404 with Zed's replay patch has green local/hosted gates; [R16_ACCEPTANCE](integration/R16_ACCEPTANCE.md) preserves exact identities and remaining HOLDs. Publication, pure-service tests and editable briefs do not establish an authenticated mounted executor or trading approval. Current engineering/operational boundaries are in `integration/COMMISSIONING.md` and the current ZED_STATE. Required producer contracts:

| Contract | Required identity / refusal behavior |
|---|---|
| Account/entitlement | Actual account/venue/product access, observed time, connection/expiration reasons; unknown remains unknown. |
| Preflight | Owning exact OSI, quotes/clocks, increment/multiplier/provenance, budget/costs, account/permission/session/policy; refusal rather than guessed values. |
| Immutable intent/approval | Server-issued immutable identity, authenticated approver, policy/scope/validity and chosen PUBLIC_NATIVE_AGENT or FLOWW_BACKEND; material changes invalidate approval. |
| Execution receipt | Original broker orderId/payload identity, actual fills/fees/protection, partial/unknown/cancel/replace/reconciliation; no fresh identity after ambiguous dispatch. |
| Ownership inventory | Observed native workflow/positions/orders and unresolved overlap; local UI lease cannot control workflows created elsewhere. |
| Session | New-entry pause 11:30–14:00 America/New_York with actual exchange/calendar/cutoffs; exits/protection/reconciliation continue. |
| Replay durability | Manifest+owning display envelope, exact Raw/Adjusted pair, gaps/window, storage health and restart-proven fixture IDs; capture independently disarmed. |

Consumers must not repair mismatches by editing producer files. Schema/route changes need a single writer acknowledged in both owner checkpoints.

## Owned additive consumer interfaces

- `lodestar-trace.v1`: requested settings, effective settings only after bridge verification, context/input SHA256, correlation/turn, evidence/observation IDs, latency/usage/status and unknown monetary cost. No private chain-of-thought or broker credentials.
- `trade-plan-draft.v1`: deterministic saved research draft; owning exact contract and raw wall bounds come from admitted backend facts. Quantity, limit, account, execution owner, confirmation and approval are UNSET; `executable=false`. This is not `execution-intent.v1` and cannot submit an order.
- `native-handoff.v1`: authenticated private operator report under `/api/agent/handoffs`; bound to the owner's completed exact-contract draft/context hash, idempotent content identity, explicit native owner, editable dated brief/reference/reported status. Broker verification is false, activation unverified, approval null. Reads are owner-scoped; revocation clears frontend views/late responses.
- `tidehunter-public-review.v1`: owned separate review consumes Pro's published selector, resolves a NEW bounded owning record and exact contract before opening, then uses the existing owner-token screen store/active lifecycle. Ckey/premium/conviction are never execution facts. Unmarked Pro v2 contexts remain refused.

The current `/heatmap` next-listed scope is day-only and does not combine with DTE/scalp/swing. The `/data` polling alias has no expiry_scope parameter; the consumer uses `/heatmap` for Next rather than silently accepting loaded scope. The optional cumulative DTE query is validated at30 by the route; unfiltered returned expiries are count-based and are not globally capped at30DTE. PR103 `611f3c2f` supplies `coverage-read.v1` stored NY session inventory, first-N listed-expiry admission and exact owning-pair admission. These read-only contracts are consumed below; a complete14–60 range-map projection remains a producer dependency, not a frontend-calculated substitute. Replay rejects missing owning ticker/record identity and restores persisted staleness/age, leaving historical freshness unknown when absent. The coarse last-two `/attribute` comparison is not a source/scope/model/population admission contract; the consumer now fetches the exact `from.id`/`to.id` admission before displaying any arithmetic. Unsupported versions, refused/missing/mismatched pair identity and late responses show no numeric result.

## coverage-read.v1 consumer boundary — R17

Frozen producer PR103 `611f3c2f71525d03ea77c5252c1c81642d424072`, composed with main6eaa3343 (includes90f96227) and PR101dcbc1492. Zed acknowledges Spark's generated-doc boundary for only the three new read-only paths (379 total); no producer/shared file mutation by Zed.

| GET /api/solstice/price-paths | Accepted shape / consumer behavior |
|---|---|
| `/sessions?ticker=` | `version`, exact `ticker`, `n_days`, `days[{date,n_snapshots,first_asof,last_asof,latest_snapshot_id}]`. On-demand NY index, explicit empty/error/version/identity states. Choosing a date exits replay and resets manifest/selection. Symbol change resets date, aborts inventory and discards late responses. |
| `/comparable?baseline_id=&snapshot_id=` | Version required; only literal `admitted=true` plus matching pair IDs admits the last-two arithmetic. Refusal reason/detail is visible; no number survives a new request, step, symbol/session change or Live exit. Missing-store/NO_BASELINE refusals may omit IDs; never admit them. This is coarse wall comparison, not price/IV/flow causality. |
| `/expiries?ticker=&min_dte=14&max_dte=60&expirations=12` | Exact ticker/window/version, explicit non-stale fetched observation, listed dates/DTE/admission/reason/count. Read-only disclosure; never changes owning selection, invokes model or fetches during replay. First12 listed expiries is NOT exhaustive range coverage. No records returned does not prove no expiry exists. |

Residual producer issues: NY index versus timestamp-prefix manifest/attribute can disagree for overnight/offset records; expiry range accepts reversed bounds and firstN listing may contain no14–60 dates despite later listings. Range inventory has no admitted display-envelope projection, and comparable query identity does not add independent metric-population metadata. Spark owns these; no live durability claim follows from index counts or fixture admission. Fixtures are explicitly synthetic in `frontend/src/fixtures/integration/coverage-read.v1.json`.

## Native Public handoff

Until official create/invoke/continuous external-GEX support is verified, an editable dated brief is manual handoff only. Clipboard success = copied, not delivered/active. Workflow reference/status is operator-reported unless supported external evidence verifies it. Public native model is independent of Lodestar. All production policy fields start UNSET; no NRG/KTOS sample defaults.

## Acceptance

Separate red/green behavior fixtures, real browser checks, authenticated provider settings, restart durability, exact combined-head full CI/security/container gates and live commissioning. No lane-only or prototype pass is combined acceptance. No auto-merge/deploy/arming/orders. Actual option PnL is distinct from underlying barrier outcomes; engineering acceptance is not profitability.

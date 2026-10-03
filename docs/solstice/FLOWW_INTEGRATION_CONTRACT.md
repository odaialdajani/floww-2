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

The current `/heatmap` next-listed scope is day-only and does not combine with DTE/scalp/swing. The `/data` polling alias has no expiry_scope parameter; the consumer uses `/heatmap` for Next rather than silently accepting loaded scope. The optional cumulative DTE query is validated at30 by the route; unfiltered returned expiries are count-based and are not globally capped at30DTE. PR103 `93dc0ef0` supplies `coverage-read.v1` stored timestamp-prefix day inventory with separate NY attribution, first-N listed-expiry admission and exact owning-pair admission. These read-only contracts are consumed below; a complete14–60 range-map projection remains a producer dependency, not a frontend-calculated substitute. Replay rejects missing owning ticker/record identity and restores persisted staleness/age, leaving historical freshness unknown when absent. The coarse last-two `/attribute` comparison is not a source/scope/model/population admission contract; the consumer now fetches the exact `from.id`/`to.id` admission before displaying any arithmetic. Unsupported versions, refused/missing/mismatched pair identity and late responses show no numeric result.

## coverage-read.v1 consumer boundary — R17

Current frozen producer PR103 `d8ba5b7b533667520274a6396b7b73da4db9bad2` (Spark MUSE_STATE §23–33; strict approval35939a6e, recovery-surplus/count-dedup a9e794ca), composed with main6eaa3343 (includes90f96227) and the prior Zed consumers at tested CODEaadea4ac. Zed acknowledges Spark-owned generated docs for the admitted read-only routes (380 total); no producer/shared file mutation by Zed.

| GET /api/solstice/price-paths | Accepted shape / consumer behavior |
|---|---|
| `/sessions?ticker=` | `version`, exact `ticker`, `n_days`, `days[{date,n_snapshots,first_asof,last_asof,latest_snapshot_id}]`. On-demand stored timestamp-prefix day index, explicit empty/error/version/identity states. Additive `ny_date` (nullable) and `overnight` (boolean) disclose NY attribution without changing the owning `date` sent to manifest/attribute. Missing legacy attribution remains unknown; a mixed NY date stays mixed/unknown, never inferred. Choosing a date exits replay and resets manifest/selection. Symbol change resets date, aborts inventory and discards late responses. |
| `/comparable?baseline_id=&snapshot_id=` | Version required; only literal `admitted=true` plus matching pair IDs admits the last-two arithmetic. Refusal reason/detail is visible; no number survives a new request, step, symbol/session change or Live exit. Missing-store/NO_BASELINE refusals may omit IDs; never admit them. This is coarse wall comparison, not price/IV/flow causality. |
| `/expiries?ticker=&min_dte=14&max_dte=60&expirations=12` | Exact ticker/window/version, explicit non-stale fetched observation, listed dates/DTE/admission/reason/count. Read-only disclosure; never changes owning selection, invokes model or fetches during replay. First12 requested listings are NOT exhaustive range coverage. Additive `coverage` validates requested/returned/filter counts and literal cap/edge booleans; absent legacy metadata remains unknown. Row `display_envelope` is only optional 0–30DTE-filter eligibility (Within/Outside/Unknown), NOT a persisted analytical display envelope. Observed edges and a below-cap result do not prove complete intermediate coverage. Top-level `chain_unavailable`/`REVERSED_WINDOW` refusals stay visible. Optional `range_map` is validated as a listing projection: exact version/window, sorted admitted date/DTE pairs and min/max bounds, literal complete flag and reason. Producer complete is a reported count/edge heuristic, not independently exhaustive coverage. The UI labels it listing-only and supplies no metric grid, analytical projection, contract selection or replay record from it. No records returned does not prove no expiry exists. |

Resolved at93dc0ef0: session index now uses the owning stored prefix and discloses uniform/mixed NY attribution; reversed expiry bounds refuse422 before fetch. Residual producer issues: firstN listing may contain no14–60 dates despite later listings. Count/edge/filter metadata does not supply a complete admitted range-map analytical projection; comparable query identity does not add independent metric-population metadata. Spark owns these; no live durability claim follows from index counts or fixture admission. Fixtures are explicitly synthetic in `frontend/src/fixtures/integration/coverage-read.v1.json`.

## lifecycle-inventory.v1 — authenticated read-only review

Committed Spark PR103 `044ca009b5343bd1013d446718516be63c393235` adds `GET /api/public/execution-lifecycle/inventory` to the already-mounted public_brokerage router under existing `require_api_key` (unconfigured503, rejected401). Spark's MUSE_STATE §23 supplies the exact writer/route boundary; ZED_STATE acknowledges this read-only boundary only. No server.py edit, approval write, recovery or broker transport is authorized by this consumer.

The on-demand Public review validates the version, literal arm/store/protection flags and local count/row shapes. It resets on account/connection changes, key/session revocation and unmount, aborts pending reads and discards obsolete responses. Current account attribution is explicitly unavailable because this producer supplies no account ID; receipt time is a local client clock, not vendor/producer observation time.

Intent rows, approval fields, drafts, cached contexts and native registrations are process-local reports. The optional stored nonterminal count is not rehydrated/reconciled here. `durable=true` denotes a registered store, not production restart proof. Empty/storeless/local terminal data does not establish no broker orders/positions or safe ownership. Approval fields are not authenticated permission; native registrations are not verified remote workflows. Production account-wide values remain UNSET. Additive installed-policy reports are accepted only as `account-policy.v1`/literal set=true/valid update time; they do not verify account binding, values or enforcement. Optional stored/revoked approval counts and native-support matrix require valid typed counts/flags/text; absent legacy fields remain unavailable, not zero/verified. Stored nonterminal rows exceeding local open plus unknown records disclose RECOVERY_REQUIRED review, even when settled history or partially recovered rows exist. Equal/unknown counts do not establish safety or reconciled ownership; the read executes neither recovery nor entry. Weekday pause status is not exchange-calendar enforcement. Reported arm state is disclosed but cannot be changed by the UI; FLOWW_BACKEND entry remains unavailable. This inventory does not close the authenticated/default-deny account-wide execution/protection/recovery contract. Committed service controls include policy ceilings, stored/revocable approvals, durable-surplus recovery admission and unique approval counts. Strict missing-store/missing-row/query-failure approval refusal is now implemented for explicit strict callers; legacy defaults remain distinct. Residual authenticated mounting/write admission, required policy/approval persistence and recovery-query failure behavior, remote inventory/risk and verified protection still require producer acceptance.

## Strict stored-approval service boundary — R17 pass 5

Spark adds `require_stored_approval=False` to injected `submit`/`supersede`; this is an opt-in service parameter, not a route, authenticated permission field or consumer mutation. With the parameter true, the presented approval must resolve to the durable unrevoked row binding intent hash/account/scope/expiry: `APPROVAL_NOT_STORED`, `APPROVAL_INVALID` or `APPROVAL_STORE_UNAVAILABLE` refuses. Supersede pre-validates before cancellation and forwards the flag. The independent ten-case probe and Spark hardening tests close pass-4's missing-row/query-failure issue **in strict mode only**. Legacy `verify_approval` and default submission flags are intentionally unchanged.

A future accepted executor must obtain an authenticated stored approval and explicitly require strict approval plus fresh preflight; it cannot infer permission from the inventory or a supplied copy. This pass authorizes no new broker-reachable mount. Best-effort policy/approval writes and unknown durable recovery counts still require fail-closed acceptance at that boundary. [Pass-5 acceptance](integration/R17_PASS5_ACCEPTANCE.md) separates those controls from operational commissioning.

## Native Public handoff

Until official create/invoke/continuous external-GEX support is verified, an editable dated brief is manual handoff only. Clipboard success = copied, not delivered/active. Workflow reference/status is operator-reported unless supported external evidence verifies it. Public native model is independent of Lodestar. All production policy fields start UNSET; no NRG/KTOS sample defaults.

## Acceptance

Separate red/green behavior fixtures, real browser checks, authenticated provider settings, restart durability, exact combined-head full CI/security/container gates and live commissioning. No lane-only or prototype pass is combined acceptance. No auto-merge/deploy/arming/orders. Actual option PnL is distinct from underlying barrier outcomes; engineering acceptance is not profitability.

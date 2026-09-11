# Lodestar: agentic AI implementation plan

Revision 4 - 2026-09-11 - revised from the Claude Code planning session.

**User priority update,2026-09-11 22:22 UTC:** Stop work focused on mobile
optimization. Prioritize desktop research, real data, AI acceptance and the
remaining AI features. Retain completed fixes; no mobile rollback was requested.

**Purpose:** Give Solstice and Tidehunter Pro an assistant that understands the selected market, joins reliable evidence, explains changes, proposes specific trades, records its calls, and earns its way toward supervised execution.

**Status (2026-09-11 implementation update):** Research is implemented and exercised with actual Public market data, managed ChatGPT login, durable local storage and both real dashboard contexts. The research release is **not accepted**: the completed independent comparison did not establish a usefulness improvement, and a fresh comparison remains unrun. Capability expansion, proposals, paper trading, proactive delivery and later live release remain incomplete/gated. No trading-performance certification or live authorization is implied. See [current delivery evidence](../INTEGRATION_AI_UI_GOAL.md) and [complete section sweep](../eval/ai-plan-sweep-20260911.md).

**23:18 update:** The fresh 30-case inputs and executable are now sealed and independently checked; all 30 route/storage input checks passed with zero candidate calls. One candidate needs 26 calls; the shared unchanged daily allowance has 6 remaining after the real selected-cell desktop check. The allowance question is pending. The [full remaining-work record](../eval/full-scope-remaining-20260911.md) preserves the entire requested scope, including the unresolved checklist contract, later-entry reconciliation and future catalog/proposal/paper/watch/live work. These are not silently counted complete by the desktop repairs.

Project root: `C:/Users/DARK HERO/Desktop/FLOWW2.0`.
Canonical plan: `C:/Users/DARK HERO/.claude/plans/i-would-like-to-replicated-stardust.md`.
Original preserved as `i-would-like-to-replicated-stardust.v3-before-review-2026-09-11.md` in the same directory.
Source baseline: HEAD `1a512c335757cc0dbccb35fd7e0a2bc728568498`, plus the current uncommitted working tree inspected on 2026-09-11. Shared files are changing; recheck them before implementation.

Planning review completed on 2026-09-11: three independent scoped code reviews, a second pass against this revised design, incorporated corrections, and a final document consistency check. See `C:/Users/DARK HERO/Desktop/FLOWW2.0/.planning/unknowns/lodestar-plan-review-2026-09-11.md` for that historical review. Subsequent implementation evidence is recorded in the current delivery document above; the original requirements below remain intact.

### User-directed transport update

The user's later instruction, "use the openai oauth", supersedes the initial OpenRouter transport choice. Production research uses the installed Codex app server's managed ChatGPT login, with verified supported model/depth/speed choices and owner-scoped saved preferences. Dollar charges are not reported by that subscription path: display unknown dollars, retain actual reported token usage and reserve a durable maximum of 40 model calls per UTC day. Do not describe subscription use as free or claim that the original monetary comparison gate passed. The $20/day OpenRouter guard remains for its optional legacy path; it does not measure ChatGPT subscription charges. Baseline/stronger-candidate acceptance and any change to the daily allowance remain explicit work.

## 1. Decisions and the revised approach

The user asked to reconsider the approach and details while keeping the intended product complete. Keep the product goals; replace assumptions that fail against the code or current provider documentation.

| Decision | Revised commitment |
| --- | --- |
| Where it lives | One shared assistant in Solstice, Tidehunter Pro, and the command bar; no separate application. |
| What it does | Research, concrete trade proposals, paper staging, proactive briefings, measurable outcomes, then separately authorized human-confirmed live orders. |
| Universe | Any requested ticker may be researched. Availability is declared by capability, entitlement, session, horizon, and source; equal treatment never means invented coverage. |
| First useful release | One complete, evidence-backed research workflow, including saved answers and minimal outcome recording. Finish this before expanding the catalog. |
| Agent behavior | A bounded tool-use workflow over existing market services. The model may request a small follow-up investigation; the server controls every capability and limit. |
| Reasoning | Deterministic market readings plus a separately labelled model interpretation. An agreement score is not a win probability. |
| Model cost | Preserve the adjustable $20/day default. Reserve costs before paid work and reconcile actual provider usage. No assumed free-model reliability. |
| Paper venue | Preserve internal simulation as the current default. First compare it with current Alpaca options-paper capabilities; changing that default requires a concrete decision, not an assumption that no options sandbox exists. |
| Trade shapes | Preserve calls/puts, shares, verticals, condors/butterflies and the wider existing strategy vocabulary. Support them in explicit batches; unsupported structures must be refused, never approximated as a supported one. |
| Local access | Asking remains key-free in the local application. Add automatic local session ownership; personal history is not globally public. Staging and global controls still require authorization. |
| Existing defects | No unrelated repair campaign. List each blocking dependency, its owner and affected milestone. A defective dependency must be repaired in scope or replaced by a verified agent-specific adapter before that capability is enabled. |
| Live trading | Keep it in the long-term plan. No live wiring or enablement is authorized by this document. Preserve the existing paper-only contract until explicit written authorization for the concrete implementation. |

### Why this design

| Approach considered | Decision and tradeoff |
| --- | --- |
| Deterministic dashboard summary only | Keep as the free fallback and evaluation baseline. It cannot investigate novel follow-up questions by itself. |
| Always run every tool, then ask one model | Reject. Wastes data calls, hides unavailable capabilities and repeats fetches; it does not solve evidence correctness. |
| Small bounded tool-use workflow with typed results | **Choose.** Reuses current Python services, permits investigation, and makes costs, evidence and failures testable. |
| Adopt a new agent framework or reuse AgentField as the control layer immediately | Defer. No demonstrated need outweighs migration and integration cost. Reconsider only if a measured spike proves simpler persistence, testing or operations under these contracts. Existing AgentField is not a replacement already wired into Lodestar. |
| Multiple debating models on every question | Defer. Agreement between models is not independent market evidence. Compare extra-model value against the single-model baseline before adding cost. |

These are design choices, not a claim of global optimality. Measure grounding, usefulness, cost and latency before promoting a more complex design.

## 2. Verified starting point and corrections

Do not infer completion from filenames, registered tool counts, a commit subject, or a response returning an allowed status.

| Current evidence | Consequence for this plan |
| --- | --- |
| `backend/services/agent/tools/__init__.py`: 65 registered tools; 52 point to `generic_ok`, which returns only ticker/horizon. | Catalog size is not capability coverage. Placeholders are disabled or explicitly unsupported. |
| `loop.py:run_turn` supplies zeroes to every confluence dimension and gives the model evidence keys without the underlying values. An isolated fixture probe changed the input sign but the verdict remained neutral/zero and neither reading reached the prompt. | Build meaningful facts-to-answer acceptance before any release claim. |
| The generic wrapper guesses argument order; actual heatseeker functions take spot first, and some require history or multiple ticker snapshots. | Replace introspection/retry guesses with explicit adapters and equality checks against known outputs. |
| `access/horizon.py` can call the next listed expiry today's expiry, use five expirations as a week, or widen invalid input to all contracts. | Calendar and expiry correctness gate all horizon-dependent conclusions. |
| The current chain path bypasses `FetchCoordinator`; `public_budget.py` exists, but a chain reservation is not the same as its multiple outbound requests. | Repair the shared access seam; count actual fanout, retries and fallback calls. |
| `public_api_adapter.py` floors time-to-expiry at a full day; `gex_core.py` recalculates Greeks even on provider-sourced contracts. | Preserve fractional time-to-expiry and field-level calculation provenance. Provider name alone does not establish observed values. |
| The routes seek `app.state.mongo_db`, which is not assigned; existing application storage is `server.db`. Agent writes/reads use synchronous-style calls against asynchronous storage. | Inject a real asynchronous repository; storage failure must be visible. |
| The route and loop allocate different turn IDs; whole requests are reused globally by ticker/horizon. Claim creation is not called by the loop. | One identity per request, owner-scoped idempotency and atomic final persistence. |
| Both assistant views are mounted, but dashboard selections are not published; the panel has no opener; final callbacks retain old text and receive no evidence collection. | Finish one shared conversation state and verify both real screens. |
| `services/audit_trail.py` is a best-effort insert of a timestamp string; its description does not establish a hash chain. | Do not rely on it for durable decisions or tamper evidence. Use the agent repository as the source of truth. |
| Trade/action packages are empty; watcher, claim-path recorder and resolver are absent. | These are remaining Lodestar features. Other app paper-trading functions do not satisfy these deliverables. |
| Existing option analytics, sizing, fills and journal helpers have narrower assumptions than the old plan claimed. | Reuse them only within proven semantics; see section 10. |
| ADR-0007 is alert persistence; ADR-0008 is the accepted agent research boundary. | Do not reuse occupied decision numbers or rewrite accepted decisions. Assign new numbers when the corresponding decision is actually approved. |

The inspected agent tests include checks that accept failed envelopes or several unrelated status codes. The revised acceptance suite must prove the right nonempty answer as well as the right failure.

## 3. Architecture and boundaries

Use the current backend and frontend. Initial deployment is explicitly **one backend worker with bounded concurrent turns**, not an untested distributed job system.

```text
Screen selection + question
          |
          v
Owned durable request -> bounded research service
                               |
                 trusted read-only data capabilities
                               |
                 immutable snapshots + typed facts
                               |
           deterministic readings + bounded model inquiry
                               |
                 validate -> save -> display answer
                               |
                  claims + recorded outcome paths

Validated proposal -> human stage/confirm -> separate action service
                                             |
                                     paper first; live later
```

- The model can name only registered read capabilities and validated arguments. It cannot run Python, shell commands, arbitrary URLs, broker tools or arbitrary database queries.
- Construct a narrow data-read interface at application startup. Research adapters receive only needed read functions and snapshots, never an unrestricted broker client or the whole server module.
- Prefer direct pure calculators and explicit repository reads. Extract small route-local calculations into shared functions when necessary. Avoid loopback HTTP: a route labelled read-only can still fetch paid data or mutate caches.
- Keep analytics independent of the agent. Startup composition may inject producers and schedule agent work; market calculators do not import agent state, portfolios or action code.
- Research and action packages have separate route prefixes, imports and authorization. Account preflight stays in actions. Market-data POST requests are classified by capability/path, not assumed to be order submissions merely because they use POST.
- Static dependency checks must actually traverse imports to a documented data-read seam and fail on parse errors. Complement them with outbound allowlists and patched broker calls over **all** research acceptance cases. A comment, token scan or swallowed exception is not proof of isolation.
- No new frontend packages. Preserve frozen application/model files and existing project approval rules. Shared changes need exact ownership and regression evidence; unrelated dirty files are not part of this implementation.

## 4. Data contracts, time and meaningful tools

### 4.1 One coherent observation

Create an immutable `MarketSnapshot` once per required ticker and coverage request. It includes snapshot ID, canonical ticker/contract identities, source observation times, receipt time, session, available expiries, requested interval, coverage gaps and calculation versions. Copy before enrichment so a tool cannot mutate a dashboard's cached contracts.

Share a snapshot across dependent tools and concurrent callers only when their exact data requirements and freshness permit it. Never share an entire answer because its ticker matches. A comparison uses explicitly bounded multiple snapshots and names cross-source/cross-time differences.

- Cache lookup must not trigger an implicit refresh. Interactive cold refresh is a separate budget-admitted operation; background work yields to visible dashboard requests.
- Repair/extend the existing cache/coordinator path rather than create a second uncoordinated chain loader. Verify single-flight on both cold and stale requests, including dashboard-plus-agent concurrency.
- Reserve provider requests at their true unit. One six-expiry chain may require expiration discovery, a quote, multiple chain calls, authentication, retries and fallbacks. The former three-request allowance cannot be treated as sufficient for that bundle.
- Reuse `public_budget.py` concepts, but count actual calls at a data-only boundary and cover every entry path. Its capacity comments are local assumptions, not verified provider entitlements.
- Model spend and market-data quotas are separate budgets. Global provider budget always wins over per-turn allowances. Missing budget control means cache-only, not bypass.
- Per-provider/per-tool timeouts consume a shared turn deadline. Cancelling one observer must not cancel a shared fetch still needed by other callers. Synchronous calculations use bounded executor work where necessary so they do not freeze the event loop.
- An empty alert read requires a successful store read and valid coverage. Storage failure, no entitlement, missing history and genuinely no alerts are different outcomes.

### 4.2 Time means the requested time

Use UTC instants in storage and exchange-local session labels for interpretation. Introduce one calendar service using a maintained exchange calendar, with explicit product trading and settlement cutoffs. `exchange_calendars` is the preferred candidate; pin a Python-3.11-compatible version and verify its dependency footprint in the first spike. An equity calendar alone does not define every option's settlement.

| Request | Required meaning |
| --- | --- |
| Same-day expiry | Contracts expiring in the requested current session before their verified cutoff; no matching contracts means unavailable. |
| Next-session expiry | Contracts expiring on the next exchange session, not the next date merely present in the chain. |
| Week | Expiries within the next five exchange sessions, with exact start/end shown. |
| Month | A rolling calendar-month interval with explicit dates and available coverage shown. |
| All available | The actual cached/fetched expiry range, never a claim to contain the entire option universe. |
| Numeric days or selected expiry in the screen | Convert through an explicit UI-to-domain mapping; preserve exact expiry selection where present. Do not silently fall back to all. |

Track requested horizon separately from effective coverage. Pre-open, after-close, weekends, holidays and early closes are explicit states. Preparation can offer the next session under its own label; it cannot silently relabel tomorrow's contracts as today's live trade. Invalid/missing expiry fields are excluded and counted, not treated as permission to widen the query.

Use fractional years to the verified contract expiry instant; never floor a same-day option to one day. If current shared data is unsuitable, calculate the agent's time field correctly in a verified adapter, label divergence and gate the affected metrics. Test zero/negative expiry time, daylight-saving transitions and early-close products.

### 4.3 Evidence is field-level and typed

Each `EvidenceFact` contains a stable full-content digest, snapshot ID, metric/field, scalar or bounded-series value, unit, ticker/contract, horizon/observation interval, source, calculation version, quality and reason. Preserve source timestamps separately from fetch time. Digest canonical values without truncating away meaningful content; include enough identity to distinguish changed observations.

Quality distinguishes `ok`, `stale`, `degraded`, `unsupported`, `unavailable` and `error`. Keep coverage and freshness separate from directional conviction. A failed provider is not a neutral market.

- Separate observed quote, provider-reported Greek and locally calculated Greek. Exposure estimates are not observed dealer inventory, regardless of provider.
- A quote requires correct identity/currency, both sides, valid ordering, observation age and applicable session. Quote mid is an analytical reference, not a guaranteed fill.
- Missing source observation time remains unknown: receipt time cannot establish freshness. Track quote time, open-interest effective date and bar interval separately. A descriptive capability may accept unknown-age data only under its declared degraded policy; actionable quotes require verifiable age or refusal.
- Never substitute entire dictionaries into prose. Derived facts such as distance to a level are computed server-side from compatible units/tickers/times and carry parent evidence IDs.
- Do not invent history. Snapshot comparison requires named anchors, compatible coverage and known gaps; changes caused by altered expiries or a different source must not masquerade as market moves.

### 4.4 Capability sequence

Implement a small complete set, with explicit adapters for actual service signatures. Internal calculators can remain numerous; public model tools should describe useful questions rather than expose every function name.

| Capability group | Initial research slice | Expansion requirement |
| --- | --- | --- |
| Market/session context | Spot, session, contract/expiry coverage, freshness and source quality | Broader product metadata and entitlement verification |
| Structure | GEX profile, combined GEX/VEX/charm summary, flip/nearest levels and air pockets from a coherent snapshot | Lifecycle, velocity, stacked/tug zones and advanced patterns need correct history/input adapters |
| Flow | Actual capped cached alert feed and extracted cached regime calculation | Live flow, drilldown, scan-cache, retail flow and volume each need an explicit data owner; never start a scan as a side effect |
| Volatility | Implied move and realized volatility only when their inputs are available | Surface/skew, density, consensus and related analytics need coverage fixtures |
| Changes/history | Agent-owned snapshots and prior saved readings, with honest missing-anchor states | Session-open/prior-close/prior-open anchors and multi-day completeness |
| Company | Explicit unavailable/not-requested state in the first slice | Overview, earnings, news, insider, sentiment and social flow via existing sources; excluded from automatic core bundles |
| Microstructure/model reads | Not enabled merely because a name is registered | Toxicity, imbalance, Hawkes, impact, liquidity, anomaly and current approved model output require actual coverage and health |
| Risk/strategy reads | Explain that no executable proposal exists yet | Validated positions, sizing diagnostics, scenarios, strategy valuation and data-only strategy quotes after proposal contracts |

Full scope retains the old structure/flow/vol/company/history/risk families, Trinity, dual GEX, strike cone, max-pain/drift, regime persistence, top movers, journal views and calibrated outcomes. Trinity requires coherent SPX/SPY/QQQ inputs and explicit three-ticker budgeting. Reads of portfolio/risk history require the owner identity even though they do not place orders.

Track these retained deliverables explicitly in D/E: approved model predictions with current coverage/health; portfolio Greeks; position-size and Kelly diagnostics; risk/scenario reads; data-only strategy quotations; ticker notes and recall; journal statistics; claim-history/calibration views. Account-connected reads require a separately authorized account binding, not merely an anonymous research session. Each item closes only with a meaningful input-to-answer case.

Every enabled capability has: exact input/output contract, actual service call, side-effect classification, entitlement/coverage function, budget cost, timeout, output cap, meaningful success fixture, failure fixture and one user question demonstrating value. An unimplemented capability returns `unsupported` and is not advertised to the model as usable. No successful empty stand-ins.

## 5. Bounded reasoning and answer quality

### 5.1 Turn workflow

1. Validate owner, question, screen snapshot and requested scope; assign a single turn ID and admit the durable request.
2. Load cheap context and required cache-backed capabilities for the request class. Freeze the evidence used and calculate the initial versioned deterministic reading and missing-input status. A simple spot question does not run a full research bundle.
3. Give the model **actual bounded facts**, the deterministic reading, quality states and permitted references. It returns either a structured answer or a bounded request for specific additional read capabilities.
4. Validate and execute at most one follow-up batch. It must address a named missing fact, comparison or contradiction. Do not repeatedly fetch unavailable data or escalate models to compensate for missing inputs.
5. Recalculate the deterministic reading if added evidence changed its inputs; validate the final model answer against those facts and that version. At most one repair request, within the same total caps; otherwise render the deterministic fallback.
6. Atomically save the answer, its complete bounded evidence and claim seed before emitting completion. Record actual model usage and schedule outcome collection.

Initial protective defaults, to benchmark rather than present as achieved performance: three tickers maximum per turn; eight capability invocations total; one model-requested follow-up batch; three model requests maximum including repair and retries; six-second tool deadlines inside a 120-second overall deadline. A retry consumes an attempt and reservation. Larger work is an explicit bounded research request, not silent expansion. Backend validates all limits regardless of client-supplied class or tier.

Count each capability/ticker invocation, including context, in the eight-call allowance. A grouped structure summary computes its related outputs once and counts as one; hidden repeated fetches or recursive calls are forbidden. A three-ticker comparison allocates one context and one requested metric capability per ticker, leaving two calls for focused follow-up; it does not promise three complete research reports. Snapshot acquisition is separately counted in actual provider requests. The normal model sequence is initial answer/tool request, final answer after tools if needed, then optional repair. Disable untracked client retries; reserve capacity for the final synthesis before accepting tool requests. Exhausted slots yield the deterministic result, not an extra hidden call.

### 5.2 Structured answer instead of custom sentence grammar

Replace `<<S:...>>`, string substitution arithmetic, punctuation splitting and per-sentence regeneration with a validated `ResearchAnswer`.

- The answer binds turn/thread ID, immutable screen context, covered interval, versioned facts, sections, source gaps, deterministic view, model view, invalidation and optional proposal reference.
- Sections are stable named fields: Structure, Flow, Levels, Vol, Company, What changed, Confluence, Verdict, Invalidation, Trade. Quick answers show only relevant sections; full research shows explicit unavailable states where required. Empty headings do not imply completed research.
- Use typed text/reference segments. Quantitative fields come from server evidence or checked server calculations. The model selects references and explains meaning; it does not set prices, quantities, probabilities or executable order fields through free text.
- Validate known references, finite values, compatible units/ticker/horizon, allowed sections, field sizes, permitted enums and data sufficiency. Test semantic contradictions such as calling below-flip price above the flip; citations alone do not establish truth.
- Close the free-text loophole with a small typed relationship vocabulary for directly checkable statements: above/below, rising/falling, fresh/stale, event date and availability. Compute/render those relationships from evidence. Broader causal commentary is explicitly an interpretation tied to evidence, not a claim of universally validated truth. Tests include a false categorical or numeric assertion hidden in free text despite valid citations; reject, repair or omit it.
- The browser renders typed components and evidence details, never untrusted HTML or model-generated scripts. Do not blanket-ban digits in tickers, dates or user wording; enforce quantitative claims at the typed-field boundary.
- Stream progress immediately and one validated completed answer. Partial model text is not a usable trading verdict. More granular validated section streaming is optional only after its measured value justifies added recovery complexity.

### 5.3 Deterministic view, model view and abstention

Keep a versioned evidence-agreement model, but specify every dimension's mapping and input quality. Reuse existing market calculations; do not count several transforms of the same exposure as independent votes. Add ablations for structure-only, flow-only and combined evidence.

Unknown dimensions remain unknown; do not silently insert zeroes and mark them healthy. Report coverage weight separately. Freeze the missing-input policy and the minimum required evidence for each conclusion before evaluation. Insufficient required inputs yield `insufficient_evidence`, not neutral or high-confidence agreement.

The model may disagree with the deterministic reading and must cite its reason. Save both views. No calibrated success percentage until there is enough comparable forward evidence for that exact event definition. A model's verbal confidence and a signed agreement score are not probabilities.

Free fallback uses the same validated facts, sections and missing-data rules. Missing model key, provider outage, malformed answer or exhausted budget must not change market facts or call a nonexistent briefing helper. No extra model call is needed for a factual lookup.

### 5.4 Model/provider selection and actual cost

Keep the existing async OpenRouter transport behind a narrow client. Before release, evaluate an approved inexpensive candidate and a stronger candidate on the same frozen questions. Pick by factual grounding, valid answers, abstention, tool selection, latency and actual cost. Record model ID, provider endpoint, prompt/contract version and routing settings. A changing free-model alias is not the production baseline.

Require compatible structured-output/tool parameters and validate locally even when the provider advertises strict output. Current OpenRouter documentation makes support endpoint-specific; use `require_parameters` and an approved fallback policy. Cache support is provider-specific and must be verified through returned cache usage, not assumed from a stable prefix. [Structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs), [provider routing](https://openrouter.ai/docs/guides/routing/provider-selection), [prompt caching](https://openrouter.ai/docs/guides/best-practices/prompt-caching).

Reserve worst-case admitted input/output/reasoning/retry cost atomically **before** each paid request using bounded payloads and a dated approved price ceiling. Enforce provider price ceilings where supported. If a reliable upper bound cannot be established, do not admit paid work under a claimed hard cap.

Reconcile against provider-returned usage/cost and generation identity, not total tokens times a tier constant. Missing usage or an uncertain cancelled request retains its reservation until reconciled; cancellation does not imply zero charge. Current OpenRouter returns usage automatically and offers generation lookup. [Usage accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting).

Use integer monetary units and idempotent reserve/settle/release operations. The budget is global to the configured billing account; a new local session cannot reset it. Budget-day timezone is explicitly America/New_York; pending prior-day reservations remain charged against available headroom until resolved. Lowering a cap below spend/pending work blocks new paid requests. Storage unavailable means no paid work; permit only a clearly unsaved deterministic preview if useful.

Budget arithmetic: headroom is today's cap minus today's settled charges minus **all unresolved reservations across days**, each counted once. Every model-request reservation has an immutable accounting day. Settlement charges that day and removes its reservation in one idempotent transition; duplicate settlement does nothing. Distinguish reserved/not-dispatched from dispatched/uncertain. Only a reservation proved never dispatched may expire without usage reconciliation; a crash around dispatch is uncertain. If provider usage cannot be established, retain the conservative charge/reservation for explicit reconciliation rather than reset it at midnight.

## 6. Durable requests, storage and recovery

### 6.1 One asynchronous repository

Inject the existing database at startup; await operations and asynchronously iterate cursors. Put driver-specific details behind `AgentRepository`. The app currently pins Motor 3.3.1/PyMongo 4.6.3; do not assume PyMongo's new async client exists in that environment.

Motor's upstream project documents deprecation and a transition to PyMongo Async. Record a separately tested dependency migration before broader deployed use; do not combine an untested app-wide driver swap with the first research repair. The repository contract should make the migration local. [Motor status](https://github.com/mongodb/motor), [migration guidance](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/reference/migration/).

Use document-level conditional updates with unique indexes. The current deployment uses standalone Mongo, so the research release must not secretly require multi-document transactions. [Mongo atomicity](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/).

| Record | Identity, contents and retention |
| --- | --- |
| Turn | One turn ID; unique owner/request ID plus request digest; frozen question/context, state/version, bounded events, answer/evidence, claim seed, usage references. |
| Claim projection | Unique claim ID and turn/event definition; immutable original verdict, evidence, trigger, horizon, versions; resolution is appended/versioned. |
| Structure snapshot | Ticker plus snapshot identity and observation time; actual levels/values and coverage, not only a hash. |
| Outcome path | Claim/ticker/session/source with source bar identity, raw bounded bar batches, acquisition times and gaps. |
| Preferences/session | Owner-scoped; validated preferences and automatic local-session capability hash. Global policy is a separate privileged document. |
| Model budget | One bounded billing-account aggregate with dated totals, open reservations and settled request identities; audit details projected into turns. |
| Paper/live records | Separate account/venue stores with durable order/fill/reservation identities; never mixed into the research cache. |

Store real UTC dates, schema/version fields and indexes with the feature. No TTL on unresolved claims, needed source evidence or unsettled reservations. Proposed retention: ordinary completed turns seven days; resolved claim evidence at least 90 days **after resolution**; structure snapshots 30 days unless pinned by a claim. Keep pending projections outside expiry. Cap event/fact/payload bytes well below the database document limit; reject oversize work before paid calls and archive only through verified projections.

Guarantee request retry and event replay for seven days from the request identity's validated creation time. Use a timestamped random request identity, validated for clock skew on first admission, so an expired request can be rejected even after its full turn is pruned; an expired identity never silently starts paid work again. Keep compact owner/request/digest/terminal tombstones through that window. Retain settled accounting identities for at least 90 days and longer while any related uncertainty remains; older duplicate settlement is rejected or checked against archived immutable detail, never treated as a new charge. Persisted claims remain readable for their longer retention independently of the retry window.

Save terminal completed state + final answer + evidence + claim seed + pending-projection marker + final event/cursor in **one conditional turn-document update**. Cancellation uses a competing conditional update; a cancelled turn cannot subsequently publish a completed claim. Then idempotently project the claim; a restart retries pending projection without creating another claim. Final completion may report projection pending, but must never say a claim was stored if its source was not committed. Outcome workers can discover pending seeds so the first collection window is not lost. Crash after commit but before delivery replays the same final event without repeating work.

For the model budget, atomic admission and reservation mutation occur within the same billing-account document. Prune only settled, reconciled identifiers after their durable detail projection; impose maximum outstanding entries and daily work limits. Do not replace a concurrency-safe aggregate with read-then-overwrite totals.

Existing `audit_trail` may receive non-critical copies. Canonical hashes support reproducible replay; they do not by themselves provide a tamper-proof audit trail. No claim of regulatory retention/compliance is made.

### 6.2 Work is independent of observers

```text
queued -> running -> completed
   |         |----> cancelled
   |         |----> failed
   +---------+----> interrupted (restart or lost owner lease)
```

- Pressing Ask creates and starts one durable admitted job. Opening/reconnecting a stream only observes it; no model execution on a GET connection.
- A client request ID reused with the same owner and body returns the original turn; different body returns conflict. Two different questions on the same ticker remain different requests.
- Keep bounded task handles and child work in the research service. Only a conditional terminal-state transition wins when cancel and completion race. After cancellation, reject additional model/tool work and release concurrency slots; reconcile already incurred spend separately.
- A disconnected panel detaches its observer; explicit Cancel cancels the request. Restart marks unfinished work interrupted and preserves cost/evidence records. Never automatically repeat an uncertain paid request.
- Persist bounded monotonically numbered progress events before emitting them. Resume applies to **all** event types, including completion. Heartbeats are transient and do not advance the durable cursor. Store structured errors without secrets.
- Polling the canonical turn is the fallback if streaming fails. Rate/concurrency limits cover asks, observers and background work separately; two observer connections must not start two runs.

### 6.3 Ownership and privacy

Preserve key-free local asking with a server-issued anonymous session capability restricted to loopback/local deployment and configured trusted origins. Choose an HttpOnly, SameSite cookie for the first release, Secure under HTTPS, with an explicit local-HTTP development exception; never carry it in a URL, log or prompt. Use a stable internal owner ID, a hashed revocable capability and a proposed 30-day rolling lifetime with rotation. Rotation retains ownership; expiry/logout revokes access rather than deletes history. Server-key-gated local recovery can rebind that owner's history after browser data loss; anonymous access alone cannot claim an existing owner. Validate origins/CSRF for local mutating research requests. Owner-check reads, cancellation, history and preferences, even on GET.

Remote/public deployment is a separate gate requiring verified server identity; caller-supplied email/tier is not authentication. Keep private account data out of shared snapshots. The anonymous capability grants research/history ownership only: private broker/portfolio reads additionally require an authorized owner-to-account binding. Global spend configuration, enablement and all action routes require explicit authorization regardless of local asking rules. New research exceptions must be exact method/path contracts, not a broad public prefix. Current global CORS does not allow credentials: milestone A must specify the integration-owned credentialed CORS change for agent routes and its regressions. Send credentials on agent fetch/stream calls, allow only configured exact origins, and never combine credentialed access with wildcard origins. Test both separate-port development and same-origin deployment before enabling cookie-owned work.

Enforce deployment mode explicitly: anonymous session issuance is for a direct loopback-bound local server only. A reverse proxy's loopback address is not proof of local access; public/proxied mode disables anonymous issuance and requires verified identity. Validate Host/trusted proxy configuration as well as Origin. Include a request through the deployment proxy in the local-bypass rejection tests.

Treat news, social posts, tool text, historical notes and user questions as untrusted content. They may supply evidence, never new instructions or permissions. Allowlist retrieval hosts/functions, cap content, redact credentials before prompts/storage, and test prompt-injection attempts to request orders, arbitrary fetches or hidden account data.

## 7. Screen and conversation experience

- One provider in `shell/AppShell.jsx`, one shared selected-screen store, one conversation/request action and one answer renderer used by panel and command bar.
- Persist validated personal preferences: default horizon, watchlist additions, risk setting, preferred venue, quiet hours, muted tickers, conviction/evidence filter and cards/day cap, plus explicit ticker notes. Personal choices cannot raise server risk limits, grant account access, change the global model budget or enable live execution.
- Publish ticker, exact expiry/horizon, selected contract/row, view and displayed observation time from both dashboards. Explicit user question selection wins when stated; a conflict is shown rather than silently mixing tickers.
- Freeze context on Ask. A later chart change cannot relabel the in-flight or saved answer. Navigating from SPY to QQQ keeps the SPY answer labelled SPY.
- Add a visible open control and preserve Ctrl/Cmd+K. Handle input focus, Escape, Cancel, keyboard focus restoration and screen-reader progress. Keep current packages and design conventions.
- Store the final validated answer returned by the service, not a closure over old streamed text. Render actual evidence fields with source/age/coverage details and a visible saved/unsaved state.
- Use the configured backend address in all modes. Test development's separate ports and the deployed same-origin path.
- Display a short answer first, expandable evidence and optional detail; surface stale, unsupported, missing history, prep mode, provider-down, cost-limited, interrupted and reconnecting states without pretending they are market conclusions.
- Proposal cards appear only for validated proposals. No active Stage button before the corresponding action path exists. Live controls remain unavailable until their separate gates are satisfied.

### 7.1 Companion UI plan and dealer drill-down integration

The owner requested two implementation plans: this AI plan and one complete
[UI redesign v3 plan](C:/Users/DARK%20HERO/Desktop/FLOWW2.0/.planning/mockups/tidehunter-pro-2026-09-05/PLAN.md).
The UI plan contains the whole dashboard redesign, its visual preview reference,
all UI build notes, the required dealer drill-down, chart calculations and UI
acceptance checks. There is no third build-notes plan.

The required drill-down is retained. Its detailed rendering and interaction
requirements are owned by the companion UI plan, section 5; its implementation
remains pending. The AI work owns the shared screen-context integration below,
not a second implementation of the dashboard or dealer charts.

- Publish the selected ticker, row/contract, exact expiry scope, view and
  displayed observation time from the dealer drill-down and both dashboard
  publishers through the same shared context path used by Ask.
- Ticker/Drill selection must use the actual selected row; the Dealers card
  uses the current dealer focus. Reuse the existing selection path and data
  ownership. Do not fetch a conflicting copy of the map for the assistant.
- Freeze context when Ask is pressed. A later ticker change cannot relabel an
  in-flight or saved answer, and a late result from a prior ticker cannot
  overwrite the current screen selection.
- Preserve stale, unavailable and unsupported states. The assistant cannot
  treat a missing dealer reading as zero or a mockup value as real evidence.
- Coordinate the UI-owned panel and AI-owned context handoff. Build/check
  ownership is split between these two plans, while the integration must be
  demonstrated against the real selected screen before release. The mockup
  alone does not satisfy the live integration requirement.

## 8. History, claims and proving improvement

### 8.1 Record enough to grade from the first release

Every saved answer records what was known then. Only an explicit testable prediction creates a claim; a company fact or explanation is not forced into a fake directional prediction. Every predictive verdict must either produce a valid claim seed or be labelled non-gradeable with a reason.

Freeze issue time, trigger definition, target, invalidation, horizon deadline, underlying reference price, direction, confidence meaning (if any), deterministic/model views, source versions and evidence. Different targets are separate named events; historical notes cannot overwrite prior claims. Thread history supplies capped structured prior verdicts and user notes with timestamps, not unconstrained accumulated prose.

Start path collection and a minimal resolver **in the research release**, not months later:

- Use a durable schedule/cursor for open claims and watchlist anchors; startup scans for missed work. Collect during sessions and after the actual calendar close, with idempotent overlap and provider-budget limits.
- The existing Public bars adapter lacks arbitrary date-range retrieval. Verify and implement a data-only historical-range capability or explicitly mark unrecoverable windows; do not assume a recent-bars call can backfill downtime.
- Preserve actual bar times, source, corrections and gaps. Keep the raw observations needed for ordering; daily high/low/close alone is insufficient.
- Never use pre-claim or pre-trigger parts of a bar as post-claim success. If target and invalidation both occur in the same unresolved bar, mark ambiguous; do not assume target first.
- Capture actual available structure from the producer/read seam and a budget-aware watchlist schedule. Fifteen-minute cadence is a target only where observations exist, not permission to refresh every ticker. Show the first valid anchor and missing sessions explicitly.
- Already accepted calls survive restarts; resolved records are immutable. Corrected market data creates a new resolution version with the previous result preserved.

### 8.2 Evaluation contract

Keep separate records and reports for research predictions, triggered setups, paper orders and actual fills. A correct underlying direction is not the profit on an option strategy.

| Evaluation question | Required treatment |
| --- | --- |
| Was the answer grounded? | Check actual facts, units, timestamps, expiry, coverage and supported interpretations against frozen evidence. |
| Did the claim resolve? | Show open, untriggered, win, loss, neither/expired, ambiguous, missing-data and malformed counts. Exclusions never disappear from the denominator. |
| Is probability calibrated? | Define the event first; report proper probability scores and reliability with uncertainty when eligible. Do not turn an arbitrary score into a percentage. |
| Did the model help? | Compare the same future cases with deterministic-only, simple direction/no-change baselines and model-assisted readings, including abstentions and coverage. |
| Did trade selection help? | Compare after-fee paper outcomes under the same executable quote/fill rules, exposure limits, sessions and entry policy; include the no-trade baseline. |
| Is there enough independent evidence? | Aggregate/equal-weight by session and account for overlapping tickers/horizons. Repeated correlated alerts are not independent samples. |

Freeze evaluation cases, labels and promotion rules before tuning. Separate development examples, held-out functional cases and forward sessions. Record every prompt/model/weight version. Do not retune on the final holdout and reuse it as new proof.

The former 40-session/100-claim/95% numbers were **proposed plan values, not requirements in ADR-0001**, and are not sufficient to establish tradable edge. Set sample sufficiency from the declared event, uncertainty and effect size, clustered by session. Do not promote from direction hit rate alone. Weight proposals require a preregistered comparison against the frozen incumbent, enough independent forward coverage, uncertainty reporting and human review. Wilson width alone is insufficient for overlapping outcomes. Keep rollback and a fresh forward check for each accepted change.

No fine-tuning, autonomous weight promotion or reinforcement-learning loop in the initial program. Outcome-guided improvement stays a controlled experiment.

## 9. Proactive monitoring and briefings

Use the existing scheduler through startup composition, not an inert cron file or a new uncontrolled scheduler. Durable work keys bind owner, ticker, session and observation/event version. Recover after downtime without flooding the model or user.

- Cheap deterministic checks first. Request model interpretation only for a material new condition supported by fresh facts.
- Coalesce duplicate alerts and repeated readings; enforce quiet hours, mutes, minimum evidence quality, card/day limit and global model/data budgets.
- Interactive research has priority; the watcher cannot consume the user's remaining budget unnoticed. Show spent/reserved/remaining cost.
- Morning brief combines already collected structure and explicitly budgeted company context. A company/news outage is a coverage warning, not a false claim that there is no event.
- Build notifications from saved answers so opening a card never reruns the model. Delivery while the app is closed remains out of scope unless separately requested.
- Acceptance simulates a full exchange session with duplicates, missing feeds, repeated reconnects and a low remaining budget. Count actual provider/model requests and cards; the previous fixed 60-alert/<$20 claim is a scenario to test, not an achieved guarantee.

## 10. Trade proposals, paper correctness and later live execution

### 10.1 Capability check before a custom book

The old statement that no options sandbox exists anywhere is wrong. Alpaca documents options in paper accounts and supports multi-leg options; current account entitlements, instruments, paper behavior and local integration still need checking. This does not authorize changing `alpaca_client.py` or placing a paper order during plan review. [Options capabilities](https://docs.alpaca.markets/us/docs/options-trading), [multi-leg support](https://docs.alpaca.markets/us/docs/options-level-3-trading), [paper limitations](https://docs.alpaca.markets/us/docs/paper-trading).

Before implementing the book, compare internal simulation and Alpaca paper on required shapes, instrument coverage, data entitlements, fill realism, lifecycle events, recovery, reproducibility and maintenance. Retain the internal default unless the user accepts a concrete change. Build a narrow venue interface so research/proposals are independent of that choice. Do not implement two complete books by default.

### 10.2 Validated proposals

Construct trade economics server-side from verified contracts, fresh quotes and an owner-selected account. The model may explain a thesis and request supported shape analysis; it cannot manufacture legs, quantities or risk approvals.

`TradeProposal` binds proposal/version ID, evidence/claim IDs, ticker, horizon, canonical legs, signed quantities, right/strike/expiry instant, deliverable, currency, exercise/settlement style, pricing basis and age, limit, fees, maximum-loss assessment, buying power, account/venue, invalidation, targets and expiry of the proposal itself.

- Reject the **whole** proposal if any leg is invalid, missing a quote or unsupported. Never silently drop the hedge or round a non-integer contract quantity into another trade.
- Strike selection may use walls, flip and other structure, but every chosen contract must actually be listed and liquid enough under a declared rule. A fixed percentage snap rule alone is not evidence of suitability.
- `strategy_builder.evaluate_strategy` is an analytical helper with same-terminal-payoff and fixed-contract-size assumptions. Verify same-expiry standard contracts independently before reuse. A sampled payoff-grid minimum is not a global worst-case loss.
- Calendars need time-dependent valuation and first-expiry lifecycle handling; shares need their own signed accounting; adjusted contracts need verified deliverables. Do not value them as ordinary same-expiry 100-share option legs.
- Distinguish theoretical value, quote mid and executable bid/ask. Theoretical prices may explain a structure, but cannot support a purported executable fill.
- Size from user-configured risk limits, independently verified contractual loss, fees, current buying power, existing exposure and outstanding reservations. Delta-at-stop is a separate local approximation, not the maximum-loss gate. Near-zero spread delta must never imply unlimited size.
- Probability of profit/expected value from a pricing distribution are explicitly model estimates, distinct from realized calibrated success rates.

Delivery batches: long options and long shares; then verified same-expiry defined-risk verticals/condors/butterflies and long straddles/strangles; then calendars and other separately supported shapes. Covered/cash-secured or unrestricted short structures require their own collateral/lifecycle proofs. The full vocabulary is retained, but support is earned per shape.

### 10.3 Internal paper book contract

Use a dedicated durable options-aware account model, not an extension of the current equity-only in-memory book. Keep cash, signed holdings, marked equity, reserved buying power, realized result and unrealized result separate.

For a signed fill quantity (positive buy, negative sell): cash changes by negative signed quantity times the verified premium price factor times fill price, minus fees; positions change by signed quantity. Keep the premium price factor separate from exercise/settlement deliverables, which can contain cash or several assets. Unsupported adjusted contracts are refused before entry. Slippage is represented by worse fill price **or** an explicit cash charge, never both. Net marked equity equals cash plus signed marked positions valued under their verified contract semantics. Use decimal/integer monetary arithmetic and independently calculated examples for buys, sells, open/close, partial close and reopening.

**Accounting dependency:** ADR-0003 and the current backtest implementation describe inconsistent slippage treatment; ordinary and terminal exits differ. Do not silently copy it or rewrite the accepted ADR. Before sharing accounting logic or shipping the paper book, obtain a clarifying/superseding accounting decision supported by hand-calculated cash/fill invariants. This blocks the paper milestone, not research.

- State changes, reservations and stable fill/order IDs must be atomic per account. On the current standalone database, use a bounded account aggregate with version checks and idempotent fill identities, then project append-only history. Define document/entry limits and recovery before implementation. If scale requires multi-document transactions, introduce and verify the deployment change explicitly.
- Maintain durable risk state per account **and venue**, keyed to the exchange session, with refreshed equity, peak equity, day losses, open/pending exposure and uncertainty. The existing process-singleton `auto_trade_risk` is not sufficient unchanged.
- Fill rules use actual eligible quotes, age, spread, displayed size, limits, fees and declared latency. Include partial, unfilled, rejected and cancelled orders. Random process hashes and generic share-slicing formulas are not option execution proof.
- Same-expiry multi-leg atomic fills are a labelled simulation assumption unless the venue provides them. Otherwise model temporary residual leg exposure. No fabricated perfect midpoint fills.
- Specify and verify expiry, early exercise/assignment, cash settlement, delivered shares, corporate actions and dividends **before** advertising a product as paper-tradable or admitting its first order. Unexpected missing lifecycle data retains holdings and reservations, blocks new exposure and marks affected results unknown with visible counts; it cannot erase a position or count as proven performance. Closing-before-expiry is a policy with failure handling, not proof assignment cannot happen.
- Journal entries are projections keyed by structure/trade/leg/fill identity. Existing contract/date deduplication and symbol-wide close functions must not collapse separate trades or calculate option profit from underlying levels.
- Acceptance: proposal -> human-confirmed paper order -> fill(s) -> durable positions/cash -> restart -> journal projection -> linked claim, all with independently correct economics.

### 10.4 Later human-confirmed live path

The research tools never obtain a live-fire capability. All actions live under `/api/agent-actions/` with explicit authorization on every method. Public's documented preflight is an estimate, not a reservation or guaranteed execution price. No Public sandbox was established by this review; never infer one. [Public preflight](https://public.com/api/docs/resources/order-placement/preflight-single-leg), [Public documentation](https://public.com/api/docs).

Live implementation requires a separately approved boundary decision extending the research decision, the accepted forward-performance policy and explicit written authorization under the existing money-path rules. Editing this plan does not satisfy those approvals.

The future submission path must fail closed on all of these checks, with the environment enable switch first in the fire handler before any order-side I/O:

1. Live environment enablement and account/venue policy are explicitly on; missing means refuse.
2. Authenticated human confirmation binds the exact proposal version, account, venue, legs, quantities, limits, expiry and allowed price movement. A short-lived single-use token is not a substitute for durable order identity.
3. Verified trading/product window, fresh valid quotes, current broker account state and required permissions.
4. Durable account risk gate, loss limits, buying power and open/pending/unknown exposure. Credit premium alone is not risk or required collateral.
5. Broker preflight succeeds and the confirmed economics remain valid; material changes require a new confirmation.
6. Validate the current aggregate risk/caps and record durable intent plus reservation in the **same conditional atomic account transition**, with a stable broker order ID and an idempotent state machine. Separate pre-check and later reservation writes are insufficient.
7. Per-order and per-day exposure/loss/cash rules include reserved, working, partly filled and uncertain orders. Immediately before outbound submission, recheck live enablement, policy and confirmation/proposal expiry after any slow preflight; invalidation releases only reservations known not to have been submitted.

After submission, reconcile order status and fills. Timeout/crash means **unknown**, not failed: keep reservations and query the broker before any retry. Consuming a nonce does not provide exactly-once delivery across a network. Duplicate fire, partial fill, rejection, replace, cancel and fill-after-cancel races all need state-transition tests.

Disabling new entries must preserve separately authorized human cancellation and risk reduction. A cancellation request is not a confirmed cancellation. Never hide a live position because the research service is disabled. Stage/fire/cancel/replace require their own concrete permissions; the model cannot grant them.

Forward promotion requires realistic paper outcomes, operational reliability, coverage, independent-session uncertainty and comparison with frozen baselines, in addition to human approval. Research accuracy alone never unlocks execution.

Insufficient or negative forward evidence means no promotion. Research and paper use can continue under their existing limits; the system must not keep tuning until it manufactures an apparent pass.

## 11. Build order and completion gates

The work below is the retained build order. Contracts and the bounded research workflow have substantial implementation evidence; first-release acceptance remains open. Later gates must not be marked complete from research unit checks. Consult the dated delivery record for current results rather than treating this table's requirements as completion claims.

| Milestone | Work and ownership | Exit evidence |
| --- | --- | --- |
| A. Contracts and failing examples | Agent contracts/access/repository design; exact shared-file ownership; calendar/model/provider capability checks; fixture inventory; migration and dependency register | Reproduce the placeholder, wrong-input, zero-score, wrong-horizon, duplicate-turn and missing-storage cases offline. Freeze typed contracts, bounded defaults and expected good/failure outputs. |
| B. Complete research slice | Agent adapters, snapshot service, repository, owner/session binding, request identity, atomic terminal states/cancellation, bounded loop, deterministic fallback and real confluence inputs; minimal UI connection and shared dealer drill-down context in section 7.1 (dashboard rendering owned by the companion UI plan) | A request on each tab uses selected ticker/expiry, returns meaningful cited facts, survives model/data degradation, saves/reloads correctly and respects actual data/model budgets. No claim of full catalog. |
| C. Research release proof | Path collection, minimal resolver, recovery/isolation fault tests, both final AI views with the section 7.1 dealer drill-down context handoff, evidence inspection, fresh independent review | All applicable research checks in section 12; one real authorized read-only end-to-end question per tab and restart/reconnect proof. Versioned baseline and actual cost/latency recorded. **B plus C is the first release.** Paper/live checks gate F/H, not C. |
| D. Capability expansion | Explicit adapters for the remaining catalog; company, microstructure, history, multi-ticker comparison and advanced structures; data-only newer bars/strategy-quote work where needed | Every added capability has a meaningful fixture, a missing-data case, entitlement/budget checks and a user question. Regression suite stays valid. |
| E. Concrete proposals | Proposal contracts, independent economics, supported-shape batches; paper-venue comparison and accounting decision | No missing-leg acceptance, false maximum-loss claim, theoretical executable quote or unsupported strategy. Every displayed proposal reproduces its economics. |
| F. Durable paper trading | Chosen venue/book, reservations/fills/lifecycle, protected human staging, journal projection, account risk | Complete paper lifecycle and restart/concurrency tests; no duplicated fills or reset risk limits; independent cash/equity oracle passes. |
| G. Watch, briefs and learning | Budget-aware scheduler, deduplicated saved cards, calibration views, frozen forward comparisons and reviewed weight proposals | Full-session simulation within limits; honest resolved/unresolved reporting; candidate change beats declared baseline with sufficient independent evidence before promotion. |
| H. Separately authorized live release | Concrete live decision, order state machine, broker capability validation, protection/operations runbook and approved performance policy | No live enabling during implementation tests; all failure/replay/crash cases proven against a simulator, followed by explicitly approved controlled rollout. |

Dependencies: A -> B -> C; D follows the stable research contracts. E can be prepared after C; F waits for E and the accounting/venue decisions. Watch/brief work can proceed after C with available D capabilities; calibration starts collecting in C and only promotes changes in G. H waits for F, sufficient forward evidence and its separate authorization. Do not make unused company/microstructure feeds block a working core research release.

Shared touchpoints are integration-owned, not edited concurrently by every feature lane: `backend/server.py`, `backend/auth.py`, cache/coordinator/data adapter, scheduler composition, `frontend/src/shell/AppShell.jsx` and the two dashboard publishers. Agent-specific files live under `backend/services/agent/`, `backend/routes/agent.py`, `frontend/src/agent/`, versioned config and focused tests. New modules should follow responsibility boundaries; do not create a service per tiny function merely to reproduce the old layer count.

## 12. Acceptance and operational checks

Use recorded, sanitized market fixtures plus deliberately synthetic failure cases labelled as such. No secret keys in fixtures, no real broker submission in tests, no broad network access during offline checks. Use a controlled test database, never production collections.

| Area | Must-pass cases |
| --- | --- |
| Real capabilities | Positive nonempty expected outputs equal the underlying calculator; placeholders and unsupported functions cannot claim success; wrong argument order fails visibly. |
| Time/coverage | Weekly-only name with no same-day expiry; holiday, half-day, before open, after close, DST, malformed expiry; fractional expiry time; unsupported index/adjusted contract; no horizon widening. |
| Shared data | Simultaneous cold requests, stale dashboard plus agent, comparison tickers; actual outbound-call count matches reserved fanout; no mutation of shared contracts. |
| Grounding | Actual values reach model; changing an input changes the relevant deterministic reading; unknown reference, stale claim, wrong unit/ticker/horizon, contradictory comparison and unsupported probability are rejected or abstained. |
| Spending | Two requests racing the last budget allowance; retry/repair; disconnect/cancel; missing usage; restart/day rollover; prior-day settlement; multiple-day uncertainty; crash before dispatch; duplicate settlement after archival; cap lowered; store down. No silent accounting reset. |
| Identity/storage | Same request/body twice, same ID/different body, expired identity after pruning, two questions on same ticker, two owners, capability rotation/recovery, proxy bypass, failed final save, restart before projection, repeated projection, document-size boundary. |
| Observers | Two streams before work completes; resume before/during/after completion; polling fallback; cancel/completion race; interrupted work never automatically recharges. |
| Screen | Both tabs, exact expiry/numeric-day mapping, chart change mid-request, visible opener, keyboard/focus, real evidence inspection, saved answer reload, both backend-address modes. |
| Dealer drill-down integration | Selection from Vector, Pulse and the Dealers card publishes the correct ticker/contract/expiry/observation; Ask freezes that context; later selection or stale responses cannot relabel the answer; missing observations remain unavailable. Chart, layout and control acceptance belong to section 5 of the companion UI plan. Both sides must pass their checks; mockup presence alone is not acceptance. |
| History/outcomes | Missing anchor, changed expiry coverage, delayed/missing/corrected bars, mid-bar issuance, both levels touched, untriggered/expired setups, overlapping claims and data outage. |
| Research isolation | Every research question cannot reach order/liquidation methods, actions, arbitrary network destinations or another owner's data; injected news instructions do not change permissions. |
| Paper | Long/short signed cash tests, partial close/reopen, fees once, close/expiry/assignment, invalid hedge, unfilled limit, unknown data, duplicate fill, restart and cap race. |
| Future live | Every required check missing/false; double confirmation, expired token, uncertain submit, restart reconciliation, partial fill, cancel/fill race, stale preflight and retained reservations. |

Keep the existing hard project checks: truth audit, pinned lint/security rules, backend tests and required total coverage on Python 3.11, frontend tests and build. Do not raise runtime pins, weaken failures, or add skips to obtain green results. Record exact commands/results and baseline failures; existing unrelated failures are not permission to claim an overall pass. Local Python 3.13 success alone is insufficient.

At release, report model factual error/abstention/coverage counts by scenario, time to first progress, time to validated answer, actual model cost, provider requests, saved-answer success and recovery results. Freeze a held-out functional set of at least 30 representative prompts plus the deterministic critical cases above; expand when new capabilities land. This is a coverage floor, not statistical proof of trading skill. Any critical grounding, ownership, budget or order-isolation failure blocks release. The first candidate must improve usefulness over the deterministic baseline without weakening those invariants.

Do not run full application checks merely to certify this **document revision**. During implementation, capture full check output and exercise the real user path. No milestone closes on mocks or status-code checks alone.

Deployment: versioned feature flags for research, background work, paper actions and live actions; default later features off. Expose readiness, degraded-data reasons, budgets, active/queued turns, reconciliation backlog and path gaps without private prompts. Use bounded concurrency and one worker until shared leases/budgets have been implemented and tested. Back up durable stores and test restoration; rollback disables new work while preserving history and all action reconciliation.

## 13. Dependency and decision register

| Dependency/decision | Handling | Blocks |
| --- | --- | --- |
| Wrong tool signatures, placeholders, dropped facts and zero inputs | Direct Lodestar repair within B; test meaningful output first | Research release |
| Shared fetch duplication, quota units and hidden route fetches | Integration-owned read seam; cache-only fallback until budget-admitted cold fetch is proven | Enabled cold-data tools/background refresh |
| Calendar and fractional expiry correctness | Agent-specific verified time/coverage contract; shared changes only where required and regression-tested | Horizon-dependent readings and proposals |
| Legacy snapshot/date gaps | Agent-owned actual snapshots with honest unavailable anchors; no fabricated migration history | Historical comparisons until enough observations exist |
| Existing alert-quality/ML-outcome grading defects | Do not reuse their success rates; use the dedicated claim contract | Only any feature that would rely on those grades |
| Accepted accounting decision conflicts with independent economics | Clarifying/superseding decision before shared accounting reuse; preserve accepted files during this review | Paper book, not research |
| Current database driver lifecycle | Async repository now; scoped dependency migration and compatibility proof before wider deployed use | Deployed readiness, not offline contract work |
| Current provider capability/pricing/rate/retention terms | Capability checks with dated sources and configured entitlements; unknown means unsupported/cache-only | Affected model/data capability |
| Internal versus Alpaca options paper | Compare before custom-book investment; preserve internal default until user decides otherwise | Venue-specific paper implementation |
| Real identity for remote deployment | Existing development sign-in is not proof; verified server identity and ownership tests | Public access |
| Required model, data and live approvals | Use existing authorized credentials only during approved implementation checks; never put values in documents; written live approval remains separate | Paid/venue checks as applicable and live execution |

The old 60-75 development-day total is withdrawn as a commitment. It mixed unproven reuse with missing lifecycle work. Estimate each milestone after A/B benchmarks and the paper-venue decision, separating coding effort, integration/review and forward-observation time. More agents cannot compress the necessary future market sessions.

Remaining policy values (freshness by source/product, supported shape limits, capital limits, model/provider allowlist and forward-promotion criteria) must be frozen with evidence before the capability they control is enabled. This plan specifies when and how those decisions are made; it does not invent account permissions or an investment risk setting.

## 14. Sources and review limits

Code evidence comes from the current working tree and the independent read-only reviews of data/tools, UI/storage and trading/outcomes on 2026-09-11. The earlier isolated turn probe used substituted data/model functions and no network; it demonstrates missing grounding and constant inputs, not live model quality. No broker, market-data or paid model request was made during this plan review. No frontend rendering, full test-suite pass or deployment is claimed.

Primary external references checked on 2026-09-11; recheck capabilities at implementation:

- [OpenRouter structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs): endpoint support and local validation.
- [OpenRouter tool calling](https://openrouter.ai/docs/guides/features/tool-calling): model requests tools; the application executes them.
- [OpenRouter provider selection](https://openrouter.ai/docs/guides/routing/provider-selection): capability and price restrictions.
- [OpenRouter usage accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting): actual returned costs and generation reconciliation.
- [OpenRouter prompt caching](https://openrouter.ai/docs/guides/best-practices/prompt-caching): provider-specific caching behavior.
- [MongoDB atomicity](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/): single-document conditional updates versus multi-document transactions.
- [Motor upstream status](https://github.com/mongodb/motor) and [PyMongo migration](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/reference/migration/): driver transition must be compatibility-tested.
- [Exchange calendar project](https://github.com/gerrymanoim/exchange_calendars): maintained session calendars, supplemented with product metadata.
- [Alpaca options](https://docs.alpaca.markets/us/docs/options-trading), [multi-leg options](https://docs.alpaca.markets/us/docs/options-level-3-trading), [paper trading](https://docs.alpaca.markets/us/docs/paper-trading): provider support is broader than the current local client; paper behavior still differs from live.
- [Public documentation](https://public.com/api/docs) and [preflight](https://public.com/api/docs/resources/order-placement/preflight-single-leg): current documented data/order capabilities; no sandbox or account-specific limit is assumed.

Accepted project decisions remain binding. This plan proposes later decisions where required; it does not supersede an accepted decision by implication. When implementation is requested, start with milestone A and the complete research slice, not a broad full-catalog build.

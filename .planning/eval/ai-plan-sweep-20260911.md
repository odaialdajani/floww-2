# AI plan evidence sweep - 2026-09-11

Latest23:19 follow-up: see [full remaining scope](full-scope-remaining-20260911.md)
and the top of [delivery evidence](../INTEGRATION_AI_UI_GOAL.md). Fresh30-case
inputs and execution are sealed and independently checked, with30 passing
route/storage input checks and no candidate run. The prior unbound status is
historical. Actual selected-cell save/reload now verified with16 facts. Full
research acceptance, later catalog/proposals/paper/watch/live gates remain open.

## Scope and verdict

Source plan: `.planning/unknowns/lodestar-plan-v4-review-draft.md`, revision 4. This report inventories every numbered section and subsection against the working tree reviewed through approximately 20:42 UTC. It is not a release approval, a complete security certification, a trading-performance claim, or acceptance of the companion UI plan. Files are being edited concurrently; findings require an exact-head recheck before closure.

This reviewer made no live provider/model calls and ran no broad tests for this sweep. Existing result artifacts are attributed below, not represented as newly executed verification. Only this report was written by this reviewer.

**Overall: partial implementation; full plan and research-release acceptance remain open.** Core ownership, durable research, evidence validation, actual Public provenance and managed ChatGPT selection have substantial implementations. Several initial research capabilities and evaluation gates remain incomplete; expansion, proactive cards, proposals, paper trading and future live release are not supplied by the research implementation.

Status meanings: `IMPLEMENTED / PROOF OPEN` means code exists but this review does not establish every acceptance case; `PARTIAL` means a specific requirement is missing; `DEFERRED` means a later gate remains intentionally closed; `RECORDED RESULT` refers to an existing artifact with its stated limits.

## Current concrete findings

1. **High - stale Public scanner results can be made fresh.** `backend/services/public_scanner.py:574` accepts a nonempty chain without checking its `stale` flag. The adapter intentionally returns an older cached chain on an upstream failure. `scan_slice` marks it `status="ok"`, updates volume/mid history and returns it; `scan_next` around line 660 assigns a new slice timestamp. `merge_slices` consequently reports fresh coverage for old observations. The new `_public_dashboard_scan` in `backend/routes/flowseeker.py` carries this misleading freshness into the main dashboard, and `public_market_scan` sends those rows to alert processing. Preserve original source observation/receipt age; stale failures must not refresh slice age or historical volume/mid marks. A cache hit also must not manufacture a new market sample.
2. **Medium - shared dashboard cache is not shared execution across every scanner entry.** `_public_dashboard_scan` coalesces its own callers and copies results before filtering, which is correct. Direct `/scan-public` and background `sweep_once` still call `scan_next` independently. Its lock serializes rather than shares an in-flight result, so these paths can advance multiple slices and spend multiple batches. This is not an unlimited bypass of the provider budget, but it is not proof of dashboard/background single-flight or interactive priority.
3. **Initial research scope remains narrower than the plan.** `backend/services/agent/reads.py` supplies price, coverage, estimated gamma, flips, stored alert direction and displayed-map facts. Its agreement call supplies only flow. Combined structure/volatility dimensions, cached regime, and the planned useful full sections are not implemented by this path.
4. **Dollar-cap proof does not transfer to OAuth.** `codex_model.py` explicitly reports subscription usage with unknown dollars, a global 40-dispatch daily limit and UTC accounting day. This must never be presented as satisfying the plan's adjustable USD 20/day worst-case reservation, New York accounting day, or actual dollar reconciliation. The user's newer OAuth instruction changes the transport requirement; it does not make unknown billing equal zero.

Previously reported issues now addressed in inspected code: synthetic startup producer removed; cached-price fallback and briefing/replay reads filter `public_api`; replay retains original source; source price time is separate from unknown chain time; saved-history comparisons use price fact time; exact verified closing price can produce a close anchor in `reads.py`; midpoint invalid-book guard was corrected by the parent after this reviewer's finding. These are code observations, not a rerun of all affected acceptance tests. Legacy order-book tables lack source labels; no active consumer was found in the bounded reader search, so this is dormant contamination risk rather than a proven active UI leak.

## Section-by-section inventory

### 1. Decisions and revised approach

| Requirement | Status and evidence | Remaining proof/work |
| --- | --- | --- |
| Shared in-app assistant, research first | IMPLEMENTED / PROOF OPEN: shared frontend agent components and `ResearchService` | Real screen acceptance belongs jointly to sections 7 and 12; no claim from component presence. |
| Any ticker with honest coverage | PARTIAL: request validation accepts bounded tickers; reads report missing caches | Equal entitlement/product/session coverage not established for all instruments. |
| Bounded evidence-backed interpretation | IMPLEMENTED / PROOF OPEN: typed facts, local answer validator, bounded service | Candidate usefulness and full capability scope remain open. |
| Adjustable USD 20/day default | PARTIAL: OpenRouter `SpendLedger` implements monetary reservations; OAuth uses a distinct dispatch counter | Preserve separate labels and policy; no dollar cap claim for subscription transport. |
| Specific trades, internal paper default, later live | DEFERRED: research actions/trades packages are empty; narrative refuses paper/order execution | Explicit proposal/venue/accounting and later live gates remain. |
| No unrelated repair campaign | PROOF OPEN: shared changes are visible in git working tree | Parent must retain exact ownership, requested scope and baseline-failure accounting. |

The selected bounded approach is implemented only as a narrow research slice. Multiple debating models/framework migration remain deliberately unimplemented, consistent with the plan's deferrals.

### 2. Starting-point corrections

| Original defect | Current evidence | Status |
| --- | --- | --- |
| Placeholder tool catalog / wrong function arguments | `tools/__init__.py` now advertises four cache-backed capabilities; `reads.py` uses explicit calculator arguments | Corrected for enabled slice; not completion of old catalog. |
| Zero inputs / facts absent from prompt | `research.py`, `contracts.py`, both model clients pass actual bounded facts | Improved; only flow contributes to agreement. |
| Horizon widening / calendar semantics | `access/horizon.py` uses explicit exchange-session windows and rejects invalid scope | Proof open for every product cutoff; fractional time helper exists but active Public adapter still floors `T` at a day. |
| Broken async storage and duplicate turn identity | Startup injects `AgentRepository`; owner/request identity and conditional finalization exist | Real synthetic-record acceptance artifact passes; broader deployment and recovery limits below. |
| Screen/closure problems | Shared context and returned completed answer implementations exist | Real multi-view interaction evidence owned by parent. |
| Audit-trail overclaim | Durable source records and hashes used | Hashes do not prove tamper resistance or regulated retention. |

### 3. Architecture and boundaries

`ResearchReads` receives three narrow injected reads, and research actions are separate empty packages. `ResearchService` has bounded concurrency and one-process task ownership. GET routes observe saved work; they do not start a turn. Local ownership is enforced before private reads and cancellation.

OpenRouter uses fixed metadata/completion destinations. Codex bridge starts a short-lived child with restricted inherited environment, disabled tool/plugin features, empty environments, read-only sandbox, no approval grants, structured output, configured server disabling, inventory checks, event caps and rejection of unexpected tool requests. This review found no confirmed authorization bypass. A complete proof still requires the actual installed Codex capability inventory and adversarial cases, not just configuration assertions; rejecting an unexpected execution event after it starts is not by itself preventive isolation.

Remaining architecture gates: all-enabled-capability import/outbound coverage, no analytics-to-agent dependency inversion, provider budget ownership on every active path, bounded synchronous work, and deployment discipline of one worker. No distributed leases are certified here.

### 4.1 One coherent observation

PARTIAL. Research is cache-only, deep-copies evidence and reads alerts with a timeout. Cache age is retained; Public quote source/time and chain receipt time are separate. The active Public chain budget accounts for its declared fanout, but actual auth/retry/fallback accounting and every entry path are not certified by this review. Scanner stale-age reset above is a release-relevant source-quality defect. Dashboard/background coalescing remains unproven across separate entry points. Unknown source time must remain degraded; provider receipt must not become market observation time.

### 4.2 Requested time

IMPLEMENTED / PROOF OPEN for exchange-session horizon selection, numeric ranges, selected expiry and explicit scope conflicts. `fractional_years` exists in `access/horizon.py`; the earlier source search found no production caller in the agent package. Public adapter retains `T = max((exp_d - today).days, 1) / 365.0`. Product-specific settlement/cutoff and adjusted/index contract coverage remain unsupported rather than verified. Do not mark the fractional-expiry dependency closed merely because a helper has tests.

### 4.3 Field-level evidence

IMPLEMENTED / PROOF OPEN: content hashes, units, ticker, source, timestamps, quality, parents and deterministic relationship checks are present. Public spot and chain times are distinct; fallback provider source is preserved. Midpoint validity correction needs its exact-head regression result retained. Open-interest effective date and field-level provider-versus-recalculated Greek provenance remain incomplete. Unknown chain time correctly limits exposure claims. Typed references prevent arbitrary numeric prose but do not certify economic correctness of every upstream input.

### 4.4 Capability sequence

| Group | Current coverage | Gap |
| --- | --- | --- |
| Market/session | Price and contract/expiry coverage, scope window, source age | Broader product metadata, entitlements and actionable quote validation. |
| Structure | Gamma profile/total, flip levels and displayed map readings | Combined GEX/VEX/charm, air pockets, velocity/lifecycle and full history adapters. |
| Flow | Capped stored alerts | Cached regime in the research bundle, explicit live/drilldown/retail/volume coverage and source-safe scanner proof. |
| Volatility | Not emitted by main snapshot reader | Implied move and realized volatility when valid inputs exist; later surface/skew coverage. |
| History | Saved observations, compatible price comparisons and exact close anchors | Session-open/prior-open completeness, actual collection gaps and downtime recovery evidence. |
| Company | Explicit unavailable message | Overview/events/news/sentiment adapters are expansion, not present coverage. |
| Microstructure/model reads | Not enabled by catalog naming | Health/coverage adapters and meaningful questions absent from enabled research slice. |
| Risk/strategy | Explicit no executable proposal | Portfolio binding, sizing/Kelly/scenarios/strategy quotes/journal and calibrated views not implemented by research. |

Retained Trinity, dual-GEX, strike cone, max-pain/drift, regime persistence, top movers and wider strategy families remain inventory items. Their existence elsewhere in the app does not connect them to the assistant or satisfy per-capability input/output, budget, timeout and success/failure proof.

### 5.1 Turn workflow

IMPLEMENTED / PROOF OPEN: durable admission, immutable settings/context, cheap exact-price path, evidence snapshots, model validation, terminal save and bounded overall deadline. OpenRouter allows bounded inspection/repair. OAuth intentionally permits a single structured dispatch, no model-requested follow-up batch, and unknown internal upstream attempts; this is a documented narrower workflow, not completion of bounded agent investigation. Current normal answers are descriptive/non-gradeable; claim-seed infrastructure alone does not create predictive user answers.

### 5.2 Structured answer

PARTIAL. Fact references and relationship vocabulary reject unknown references, conflicting comparisons, unrestricted prose and invalid states. The current fixed interpretations and section enums are substantially narrower than Structure/Flow/Levels/Vol/Company/Changes/Confluence/Verdict/Invalidation/Trade with typed interpretations. No proposal reference or executable trade fields are generated. Progress plus final validated answer exists; partial raw model text is not published.

### 5.3 Deterministic versus model view

PARTIAL. Unknown dimensions remain unknown and overall direction is insufficient evidence when coverage is missing. Facts are stable across model failure. However `reads.py` passes only flow into `score`; structure-only and combined-evidence behavior/ablations are missing. The model is limited to selected approved interpretations/relationships, not the full planned reasoned disagreement with a saved deterministic view. No calibrated probability or trading edge is established.

### 5.4 Provider selection and actual cost

PARTIAL. OpenRouter preserves endpoint capability/price checks and actual spend accounting. OAuth catalog/settings are owner-scoped and selected model/effort/speed are revalidated; uncertain dispatches remain counted. OAuth cannot establish dollars, a hard token ceiling, or one upstream request per app dispatch. Its UTC day and call cap are not the plan's New York monetary budget. Same frozen candidate comparison, model usefulness uplift, latency and actual-cost report remain open; a single successful authorized answer is integration evidence only.

### 6.1 Repository, retention and recovery

IMPLEMENTED / PROOF OPEN. Awaited repository, owner/request and turn uniqueness, atomic final answer/seed/event, pending projection and conditional cancellation are present. `storage-pinned-20260911-1933.json` records successful local Mongo 8.0.32 with pinned Motor 3.3.1/PyMongo 4.6.3, separate-process recovery, BSON restoration and duplicate-constraint tests using isolated synthetic databases. This does not prove server-kill recovery, production-volume backup, every retention boundary, provider calls or broader deployed-driver migration. Outcome paths in that exported fixture were empty; their real recovery proof is separate.

Claim/evidence retention, unresolved reservation retention, seven-day replay/tombstones, 90-day settled identity retention and all payload boundaries require their own test evidence. OAuth's separate collection and dispatch tombstones need explicit retention/operational policy; no dollar-settlement promise applies to them.

### 6.2 Work and observers

IMPLEMENTED / PROOF OPEN: Ask owns execution; saved streams/polling observe; same owner/request replays; cancellation races finalization; restart marks unfinished work interrupted. Disabled research blocks new asks while history/stream/cancel/logout remain accessible. User disconnect is not a restart trigger. Independent stream admission/resource limits and all reconnection phases must be verified, not inferred from bounded turn concurrency.

### 6.3 Ownership and privacy

IMPLEMENTED / PROOF OPEN for direct-loopback deployment, Host/Origin checks, exact method/path exceptions, HttpOnly SameSite capability, owner-scoped reads and privileged recovery/budget path. Model settings cannot change account access or live enablement. Remote identity and owner-to-broker binding remain closed gates. The managed local ChatGPT account is distinct from broker ownership; the child does not inherit provider credentials. All actual deployment-address and proxy-bypass cases remain part of release proof.

### 7. Conversation experience

PARTIAL / parent-owned browser proof. Shared context, immutable Ask selection, completed answer persistence, source details, visible controls and new model settings exist. No new frontend package was required. The complete preferences list is not present: current route allows horizon/watchlist/quiet/mutes/card limit/notes/AI settings, not the full risk/venue/evidence-filter product. Persisted quiet/mute/card choices are not proof a proactive delivery service honors them. Keyboard/focus, separate-port/same-origin, stale/error/unsaved/reconnect states and both real dashboards require actual UI evidence.

### 7.1 Dealer drill-down handoff

PROOF OPEN. `display_map.py` checks exact ticker, map version, query and visible selection, and degrades unknown ages. This is useful protection against mismatched answers. The required Vector/Pulse/Dealers interactions, actual selected contract/expiry/observation publication, late-response races and live Ask integration belong jointly to the companion UI plan. This reviewer does not certify those charts or interactions from backend code.

### 8.1 Claims and observed paths

PARTIAL. Claims, resolver, path collection, immutable evidence, atomic seed projection and cache anchor scheduling exist. Normal research answers are explicitly non-gradeable; no fake claim is forced. Exact close anchors are created only from a healthy price observed at the verified close. Actual historical-range capability, gaps/corrections/overlap recovery, post-trigger bars and forward session coverage need evidence beyond synthetic fixtures. Never count a displayed stale cache as a session close.

### 8.2 Evaluation

PARTIAL. Frozen 32-question offline baseline and independent agent review exist under `.planning/eval/lodestar-research-v1/`. Review explicitly distinguishes automatic contracts from usefulness and notes that cases are now development-exposed. Do not reuse them as unseen holdout after tuning. Fresh candidate comparison, forward independent-session uncertainty, denominators including abstentions/unresolved cases, after-fee paper/no-trade baselines and promotion rules remain open. No probability calibration or weight promotion is accepted.

### 9. Proactive monitoring and briefings

PARTIAL. Existing scheduler calls bounded research maintenance and defers anchor jobs while interactive tasks exist. It projects claims, collects paths/anchors and reconciles model accounting. It does not implement the complete saved-card watcher, material-change model gate, quiet-hour/mute/card-cap enforcement, company-aware morning brief, delivery deduplication and full-session budget simulation. Public scanner alert work is not automatically the owner-scoped assistant notification contract.

### 10.1 Paper-venue decision

DEFERRED. The required current internal-versus-Alpaca options-paper comparison and concrete accounting/venue decision were not established by this source sweep. Internal default remains; no venue change or paper order is authorized by this report.

### 10.2 Validated proposals

DEFERRED. `services/agent/trades/__init__.py` is empty. Full legs, identity/currency/deliverables, direction/quantity, observed bid/ask age, strategy economics, payoff boundaries, invalidation and immutable proposal version have no complete research-to-proposal path. Wider calls/puts/shares/verticals/condors/butterflies cannot be approximated into supported shapes. Independent economic examples are still required.

### 10.3 Durable paper book

DEFERRED. `services/agent/actions/__init__.py` is empty and research refuses staging. Existing app paper components do not prove this plan's signed cash, exposure/reservations, partial fills, fees, expiry/assignment, duplicate-fill handling, restart and journal/claim linkage. The complete proposal -> human-confirmed order -> fills -> cash/positions -> restart -> journal -> claim scenario remains open.

### 10.4 Later live path

DEFERRED / NOT AUTHORIZED BY THIS REPORT. Preserve all environment/account gates, exact human confirmation, fresh quote/product/account checks, atomic risk reservation, stable order identity, uncertain-submit reconciliation, cancellation/replace races and independent forward-performance approval. Actual Public market-data access does not authorize order submission. Disabling research must not hide positions or block separately authorized risk reduction.

### 11. Build order

| Gate | Sweep conclusion |
| --- | --- |
| A contracts/failing examples | Substantial evidence exists; not a blanket completion of every dependency. |
| B complete research slice | Partial: missing planned capability/answer depth and scanner source-quality issue. |
| C research release proof | Open: full checks, real both-tab path, new model comparison and independent useful-answer evidence incomplete. |
| D expansion | Not complete; narrow enabled catalog must remain honestly limited. |
| E proposals | Deferred/incomplete. |
| F paper lifecycle | Deferred/incomplete. |
| G watch/briefs/learning | Partial infrastructure; delivery and forward-promotion evidence incomplete. |
| H future live | Closed pending its separate authorization and proof. |

The plan defines B plus C as the first release. No later gate is inferred from research tests, and no mock status code closes a gate.

### 12. Acceptance and operations

Required categories inventoried: time/product scope; shared fetch fanout/coalescing; actual evidence grounding; spending/races/day rollover; identity/retention/recovery; observer replay/cancel; both screen modes; dealer context; history/outcomes; research isolation; paper economics; future live failure cases.

Existing `.planning/eval/backend-suite-20260911-1949.json` records **54 failed, 5312 passed, 71 skipped, 9 deselected, 1 error**, Python 3.11.15, coverage 67.61% against required 60%, exit 1. Coverage passing does not make the suite pass. These results predate later edits; parent must record exact current commands and baseline attribution. This reviewer did not rerun that suite. Truth audit, lint/security, frontend tests/build and current full backend result remain separate checks; no skipped/unrelated failure may be silently relabeled green.

Real storage report supplies bounded synthetic-record acceptance, not provider/model or screen proof. Current live Public/OAuth evidence must name factual validation, abstention, latency, source gaps and unknown subscription dollars. Model output rejected for a degraded comparison is a successful validator refusal, not a successful useful model answer.

Operational readiness, queue/reconciliation/path-gap visibility, one-worker limits, feature flags, rollback preserving history, backup restoration and request accounting require final exact-head review. The stated report here is partial/open, never full acceptance.

### 13. Dependency and decision register

Keep explicit owners/blockers for: remaining read adapters; scanner freshness/shared quotas; fractional expiry/product calendar; source/anchor gaps; independent claims rather than legacy success rates; paper accounting conflict; driver migration; dated model/data capability terms; venue decision; remote identity; future live authorization. New user OAuth direction supersedes a transport preference only, with its cost/tool limits documented. Freshness, strategy limits, capital policy and forward-promotion criteria must be frozen before enabling affected capabilities.

### 14. Sources and review limits

The exact revision-4 plan is the requirement source. Code anchors above identify current implementations and gaps; existing result JSON and offline baseline review are bounded prior execution evidence. External plan links were not revalidated in this read-only sweep, and no fresh provider/model calls were made. The user's newer actual-Public/OAuth request is incorporated as current steering without erasing incomplete original product scope.

This is a section-by-section inventory, not proof that every line of every dependency is correct. Final release requires resolving confirmed defects, retaining a requirement-to-test/result mapping, completing the parent-owned real UI check, and reporting all still-open capabilities and gates.

## Structured deterministic answer update - 21:28 UTC

The stable server answer layout from section 5.2 is now implemented in answer_sections.py and integrated into deterministic_answer. Full research emits Structure, Flow, Levels, Vol, Company, What changed, Confluence, Verdict, Invalidation and Trade. Targeted questions select relevant fields, and the exact-price path emits only the underlying price without extra reads. Unsupported Company, predictive verdict/invalidation and executable Trade remain explicitly unavailable; headings do not imply those capabilities were researched or completed.

Each section retains compatible text plus typed fact-reference/text segments, referenced evidence IDs, availability, non-gradeable claim status, and per-ticker/horizon/window entries with source gaps. Values are rendered from existing facts, including bounded series; long series link to retained evidence rather than inventing a summary value. Displayed-map references retain their own fact scope and existing verified explanations. New exposure and volatility metric names supplied by the backend implementation are mapped. Price alone does not make Levels available. Stale/degraded inputs remain labeled, and missing agreement dimensions do not become neutral.

Owned-history comparisons now replace their matching ticker/horizon entry in What changed instead of appending ticker-named headings. The history read, anchors, compatible facts and quality rules were not changed. Top-level facts, snapshots, gaps and immutable screen context remain intact. Model contract, interpretation transport and browser source were not edited by this batch.

Five new mounted-free backend tests first failed against the old ticker-blob output. Six new tests now assert actual displayed values, exact price isolation, relevant quick sections, multi-ticker/horizon references, stale status, missing levels, volatility values and history merge. The new file plus unchanged plain-answer/display-map/price-lookup/research-read tests pass **38 tests**; scoped Ruff passes. No network or model call was made by this batch. This closes deterministic section construction, not the remaining typed model reasoning, useful-capability coverage, predictive/proposal, held-out evaluation or real rendered acceptance gates.

## Final implementation sweep update - 2026-09-11 22:10 UTC

This update supersedes earlier open findings only where explicit. The original section-by-section inventory remains intact. The first research release and full AI plan are **not accepted**.

| Plan area | Current evidence and remaining gate |
| --- | --- |
| 1-3 decisions, real reads, source ownership | Actual Public read-only data and managed ChatGPT login implemented. Removed production mock feed startup, preserved original ingestion source, excluded unproven synthetic cache rows from live fallbacks. Separate underlying bid/ask/last times from retrieval time and option-chain Greeks/OI times. Unknown chain times remain degraded. No model tools can send orders. Production-wide shared acquisition/fanout is not newly certified by the isolated preview. |
| 4 first capabilities | Combined gamma, vanna/charm, nearest nonzero exposure levels and air pockets use actual existing calculators. Missing/floored expiry inputs refuse unsupported computations. Implied move needs verified IV and exact product expiry time; oldest-parent age propagates and future/stale IV refuses.37 new capability checks and63 related checks pass. Real Public missing product cutoff means unavailable; optional realized-volatility daily-history input is not connected to production. Wider company/microstructure/strategy/history catalog stays open. |
| 5 answers and interpretation | Stable ten sections, quick question-specific sections, exact-price bypass, typed fact references and explicit scope/quality. Model selects at most four server-checked explanation IDs and validated relationships; it cannot publish arbitrary ungrounded prose. Real model-assisted answers on both dashboards prove this path works for those questions, not general usefulness acceptance. |
| 6 bounded work, storage, privacy | Actual pinned-driver sample-record storage acceptance passed; owner/session recovery, immutable answers, bounded cancellation, unknown-spend reservation and logout behavior tested. Managed OAuth model/depth/speed are frozen per ask.40 daily calls; unknown subscription dollar cost remains unknown. Local-only identity remains the supported deployment. Remote identity/account binding are not enabled. |
| 7 and7.1 conversation/context | Actual Tidehunter selected contract SPY260914P00724000 and actual Solstice map version/query/visible scope saved with model-assisted answers. Changing page/ticker cannot rename saved evidence. Mobile modal/footer overlap and opener interception fixed and viewed; saved answer reopened after reload. Actual Solstice SPY-to-GOLD failure clears the prior ticker values, independently tested across A-to-B-to-A races. |
| 8 claims and evaluation | Descriptive answers remain non-gradeable. Projection/path/resolver primitives and bounded recovery exist; actual arbitrary historical-range collection and forward outcome coverage remain incomplete. Original30-case OAuth review failed acceptance:27 assessed pairs,0 wins/27 ties, with a ticker exclusion error later fixed. Three later exposed development cases won; preserve their non-held-out status. Fresh30-case v2 is frozen but unbound/unrun. No forward performance, win probability, weight promotion or release improvement is claimed. |
| 9 watch and briefs | Maintenance/anchor scaffolding exists. Complete owner-scoped material-change cards, quiet/mute limits, morning briefs, deduplication and full-session budget acceptance remain incomplete. |
| 10.1 venue | Current documented internal-vs-Alpaca comparison exists in unknowns/paper-venue-check-2026-09-11.md. Internal default retained; no account venue change or paper order. |
| 10.2-10.3 proposals and paper | Still incomplete. ADR0010 proposes counting slippage once in fill price, fees once, with hand-calculated cash example; owner decision pending. Actual validated leg economics, lifecycle, reservations, partial fills and full restart/journal linkage must be built and accepted after research gates. |
| 10.4 live | Separate written approval and future forward evidence still required. Off-by-default Public fire gate/auth repair is a refusal fix, not live enablement or completion. |
| 11 sequencing | Contracts and bounded descriptive research are substantially implemented; C remains open, so do not claim first release B+C or later D-H complete. |
| 12 checks and operations | Final frontend81 suites/676 checks pass, final production build passed.217 focused research checks; full Ruff and required-medium scoped security pass. Full backend run started22:04 remains pending at this writing; append actual result below. Real storage and per-tab provider/model evidence supersede the old missing-database and no-real-question blockers only. Full crash/production-scale recovery and unseen two-candidate usefulness/accounting acceptance remain separate. |
| 13-14 dependencies and sources | Preserve original capability/product/accounting/remote/live dependencies. User's OAuth choice supersedes transport selection; actual subscription dollars cannot satisfy a fictional dollar-spend result. This update uses current code, actual local results and the earlier verified official capability documentation; it does not silently refresh or expand financial claims. |

The final v2 comparison needs up to26 actual one-attempt calls for one candidate or52 for two, before any retries (production OAuth allows one application dispatch per turn). Only9 daily calls remained at22:00. More allowance alone does not create missing source/history prerequisites. Do not reset quota, fabricate snapshots, drop inconvenient cases, or call an exposed development check fresh acceptance.

Operational limits remain explicit: isolated read-only preview, local owner sessions, no enabled paper/live path, no production startup certification, no claim that every one of the424 incoming commits was audited. The full requirement inventory has been retained rather than shrinking the user's plan to the implemented subset.

### Full-run result and fixture repair - 22:16 UTC

The22:04 full run completed5486 passed,70 skipped,9 deselected,136 warnings and1 session teardown error in435.90s; coverage66.54% exceeds the60% requirement. The error is the network guard catching blocked requests from route-ordering, morning-briefing and scheduler tests, not the last VPIN test body. Machine record: backend-suite-20260911-2212.json. Guard caught and prevented those outside requests; the full run is failed.

The three affected fixtures were corrected without changing production permissions or bypassing real route/calculator/scheduler logic.31 targeted checks pass with no blocked attempt. Guard diagnostics now enumerate all originating tests instead of hiding later fixtures behind a20-example cap. Saved at45e104e4. A fresh full run began22:14; do not call it passed before its actual result arrives.

Fresh evaluation sources now include actual captured Public chains for DIA/IWM/QQQ/SPY (18 allowlisted market/auth/account reads) and all four real preview heatmap responses (HTTP200). Source files are immutable and make zero model-call claims. Capture's post-save cleanup initially used the wrong broker return shape and exited1 after saving; all four file records/hash were reread successfully and the short-lived capture process ended. No recapture or model call was used to hide that cleanup error.

The prospective v2 protocol amendment was frozen before any baseline/candidate output. It corrects an unnecessarily strict all-real-condition requirement invented by the evaluation protocol: plan section12 already permits labeled synthetic failure fixtures. Raw Public input remains unchanged; artificial stale-map/history/version conditions require separate recipes and labels. The original frozen questions/rubric/manifest are preserved. A complete bound runner and authorized extra model allowance still remain pending.

## Final checks and user priority - 22:23 UTC

Final backend at source45e104e4:5486 passed,70 skipped,9 deselected,0 errors/failures,425.57s, coverage67.52% against required60%. The session-wide external-network guard completed with no blocked attempts. Full backend Ruff and whole-backend required-medium security scan pass. Frontend81 suites/676 tests and final build pass. Truth audit23 pass/0 fail/4 skipped metadata claims remain unverified. See backend-suite-20260911-2222.json and delivery-checks-20260911-2222.json. Do not extend this result to unimplemented capabilities, unseen model quality, production-scale recovery or live trading.

User22:22:42 instructed stopping all mobile optimization, which is now removed from further work. Desktop/data/AI are the active priorities. Previously completed mobile fixes/checks remain historical; no rollback requested or performed. The model-check allowance and paper-accounting questions remain unanswered. No additional model calls or quota change occurred.

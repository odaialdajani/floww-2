# Bounded Public scan merge review

Reviewed 2026-09-11 22:50-22:54 UTC. Compared integration merge9d5e500a against local parent3b98ada0 and incoming parent7685a44b, then inspected current source. Scope: backend public_scanner/public_api_adapter and the exact deleted frontend FlowEngine/convictionUi paths. No live source, model, order, browser or mobile action occurred. Existing closed source-age/quote-validity/scanner-staleness repairs were not counted again. This is not a whole-repository audit.

## Confirmed coverage defect and authorized repair

The adapter appended each requested expiry immediately after a successful request, before checking whether that response contained any accepted contract. A successful empty response, an all-expired/all-invalid response, or a response whose actual contract expiry differed from its requested expiry could therefore advertise unsupported expiry coverage. `backend/server.py` passes `raw["expiries"]` to `expiries_used`; this metadata is presented on the desktop, so it cannot merely mean dates requested.

A read-only mocked reproduction returned reported expiries2026-12-18 and2026-12-31 while every accepted contract belonged only to2026-12-31. Existing D4 tests covered thrown expiry requests, but not successful-empty requests. Three new regression cases failed before repair; a fourth no-accepted-contract case already passed.

Parent authorized the narrow fix. `public_api_adapter._fetch_chain_live` now adds unique canonical expiry dates only after accepting a contract. Contract records use the same canonical date. A mixed response preserves valid contracts and0DTE, drops invalid/expired contracts, and derives availability from actual accepted dates. Requested fan-out limits and cache-key metadata remain unchanged; no caller requiring a separate requested-date list was found, so no speculative new field was added. An entirely unusable result still returns unavailable.

Validation:33 passed across the new expiry-coverage file and existing adapter truth, partial-data, adapter-regression, scanner-staleness and scanner-fairness files, with the offline network guard enabled. Ruff passed on the changed adapter/new test file. No production provider call was made. Source changes are limited to this accepted-expiry bookkeeping; no score redesign or scanner mutation was performed.

## Retained incoming behavior

- The scanner was added by incoming main and was unchanged by the conflict resolution relative to that parent. Current later repairs preserve finite two-sided price checks, slice receipt age, successful-empty slice clearing, old-slice expiry, fair rotation under budget trim and adapter-owned fan-out debit.
- Incoming minimum-volume/volume-to-open-interest selection and per-ticker row limit remain present. Current quote provenance preserves separate side/last observation times and unknown whole-chain observation time; this review does not treat receipt time as market time.
- Adapter requested-versus-returned expiry handling was the concrete remaining metadata defect found here. No further reproducible new score/freshness defect was established in the bounded scan/adapter read.

## Deleted frontend paths are intentional

Exact local-parent paths were `frontend/src/components/flowseeker/FlowEngine.js` and `frontend/src/components/flowseeker/convictionUi.js` (plus its test). They are absent in the incoming parent, integration merge and current tree.

Incoming commit3e737a1d and `.planning/phases/phase-7-pulse-hardening/PLAN.md` record the explicit user-directed deletion of the unmounted InstitutionalAlertsPanel cluster, synthetic FlowEngine and orphan files. The local convictionUi consumer was that removed InstitutionalAlertsPanel; FlowEngine had no retained external importer in the local frontend tree. Their deletion does not establish a lost reachable desktop feature and is not proposed for reversal. Earlier codebase-map references to their continued existence are stale.

Full combined build/tests remain with the parent. No commit was made by this subtask.
# Final integration follow-up23:22

The full backend run found an older adapter test still asserting both listed
expiries even though its broker fixture returned no contracts for October.
Updated it to assert only September usable coverage, nonempty returned expiry
identity and proof both listed expiries were requested. This preserves the
reviewed production fix and does not weaken it to accept empty coverage.
Adapter integration/truth/coverage group:19 passed under outside-network guard.
The complete run's historical failure is retained in backend-suite-20260911-2324.json.

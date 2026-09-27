# Application shutdown ordering review - 2026-09-27

Verdict: CHANGES REQUIRED for saved research shutdown ordering. Read-only review; production sources unchanged by reviewer. Scope is concrete shutdown data safety, not whole-app readiness.

## Verified actual ordering

An isolated child imported the actual application with unique unused Mongo identity, analytics memory storage, loopback-Mongo-only socket access and subprocess denial. It invoked no startup callbacks and no user/provider/model/order requests. It inspected the actual registered callbacks and installed Starlette implementation. Evidence: `output/application-shutdown-order-initial-20260927.json`; denied attempts empty.

Installed Starlette runs handlers in registration order, awaiting each, without reversing them:

1. server.on_stop
2. routes.market_catalog.stop_release_watch
3. server.shutdown_research
4. server.shutdown_duckdb
5. server.shutdown_ingestion
6. server.shutdown_solstice_capture

## Critical finding: research cancellation writes after Mongo closure

`on_stop` closes shared Mongo with `client.close()` before `shutdown_research` runs. ResearchService.close cancels active/queued work and awaits it. The worker's CancelledError branch then awaits repository.finish(... interrupted ...), which needs that closed Mongo client. ResearchService.close uses gather(return_exceptions=True), so failed interruption writes can be concealed while shutdown appears successful. Persisted running/queued records are only repaired at a later startup; graceful shutdown itself has not saved their terminal state.

This dependency/order defect is source- and registration-confirmed. Root owns the actual isolated Mongo/router.shutdown failure reproduction; this reviewer did not duplicate that execution or assert a database result not yet observed.

## Smallest correction and tradeoff

For the narrow saved-research fix, await the existing research service's close in on_stop before client.close. Look up app.state.research_service safely because the feature is optional. Its current close is idempotent, so the later callback can remain a harmless second call, or call a shared helper from both sites. Keep errors visible; do not make a save failure look like successful terminal persistence. Verify actual router.shutdown with active and queued research, read saved rows through a separate client after shutdown, and confirm each interruption is recorded exactly once before later startup.

A cleaner but larger alternative is moving shared Mongo/provider closure into a final callback registered after all consumers. This respects the dependency globally, but broadens the lifecycle change and still requires that earlier callback failures do not skip cleanup. Given the user's critical-only scope, prefer the targeted research-before-Mongo fix and retain known broader limits.

## Focused sibling sweep

- DuckDB shutdown precedes ingestion drain. However DuckDBEngine.stop only cancels its own periodic flush and flushes internal buffers; it does NOT close its connection. Ingestion's final drain writes directly through execute_write_bulk. Therefore current ordering is awkward, but this review found no proven lost rows from this order alone. Do not enlarge this fix on that assumption.
- Solstice capture registers late but is also in the shared tracked background set cancelled by on_stop. Its late callback is not by itself proof it runs against closed dependencies.
- on_stop awaits remaining tracked work for only five seconds, ignores the still-pending result, and then closes dependencies. This is a known limit: cancellation request is not proof every consumer stopped. The optional release watcher has its own HTTP client and does not depend on shared Mongo/broker.
- Heatmap stale-cache refresh uses a detached create_task without adding it to the tracked background set. Its actual build can later schedule Mongo snapshot saves and use the shared provider. Thus tracking coverage is incomplete and whole-application shutdown safety must remain unclaimed. This is a concrete source finding, not a demonstrated lost-write case in this review; retain it as a separate important follow-up instead of silently broadening the research fix.

## Boundaries

No full application startup, live listening server, user process shutdown, external call, database crash, backup restoration or trading action occurred. The actual research-worker abrupt-restart proof remains a separate passing result; it does not excuse graceful-shutdown ordering. This report makes no whole-app readiness claim.

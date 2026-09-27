# Bounded independent backend integration review - 2026-09-26

Reviewed local dba50893403922a2f82e2be7c5a2671ea8d37780 against incoming 79b28ec2, common parent7685a44b. Scope: server.py, routes/agent.py, public_api_adapter.py, heatseeker.py, gex_core.py and immediate caller/dependency paths needed to assess retained research, market provenance and new Solstice history/review behavior. This is not a review of every file in the95 incoming commits.

Method: compared both branches against common parent; inspected actual incoming Git-object source and emerging conflict list. Executed three exact incoming functions/route callables extracted into memory with explicit fake storage modules. No production source edits, server startup, provider/model/broker call or production-storage access. Only this report was written. Full suites were not run by this reviewer. Merge was still being resolved during review, so findings below are against the named incoming/local revisions, not a final merged verification claim.

## Required conflict resolutions

1. **Keep local durable owned research.** Incoming routes/agent.py, services/agent/claims.py and loop.py only add exception logging to the obsolete implementation. Taking incoming versions would restore process-global turns/old claim logic and lose local owner isolation, saved/reopened turns, cancellation, grounded answers and usage controls. Keep local behavior; optional compatible logging is not a reason to resurrect replaced code. services/agent/llm_client.py logging is independent, not a substitute for the local model boundary.

2. **Compose server changes, do not choose either whole file.** Retain local Public-only refusal before alternate-source fallthrough; cached_market_copy cache returns; immutable requested_map_query; actual spot event/fetch timestamps; chain event_time distinct from build asof; raw stale/cache-age values; and boolean sanitation. Retain startup_research/AgentCORSMiddleware, fixed copy-only readers, owner repository, shared Codex counter, shutdown_research and scheduler maintenance. Add incoming vendor-first display surfaces, truthful unknown taps, Solstice metrics/session/scout/history/capture functions, and review route registration BEFORE app.include_router. Keep production synthetic feed removed: incoming opt-in mock startup must not undo the local no-synthetic-producer decision. Capture/outcome workers remain opt-in; do not enable them as a merge side effect.

3. **Compose adapter contract handling.** Retain local _resolve_spot_observation, copied non-fetching peek, finite/two-sided quote validation, older verified midpoint-side time, timezone-aware source-time validation, exchange-close handling, and absent chain observation time. Retain incoming exact expiry clock/series, explicit index instrument type, None for missing OI/IV/volume and Greek/OI provenance. Keep BOTH source timestamp field names needed by consumers: local last_event_time/bid_event_time/ask_event_time and incoming last_timestamp/bid_timestamp/ask_timestamp. In services/public_api.py retain local Quote bid/ask timestamp fields plus incoming OptionContract metadata and typed order fields without duplicate keyword arguments.

4. **Accepted expiry coverage must survive the loop replacement.** Incoming appends each requested expiry immediately after successful fetch, even if no accepted contract. Local derives unique canonical expiries from accepted contracts only. Preserve local rule while replacing day-only expiry validation with incoming exact-T handling; do not leave an undefined exp_d reference or retain the incoming premature append. Empty, all-rejected and returned-expiry-mismatch regressions exist locally.

5. **Retain existing confirmed-fill accounting.** Incoming changed no production Alpaca client/routes, entry_fills, order_router, journal_store or close_intents paths. Preserve local broker-order identity, actual fill quantity/price, pending-zero-fill refusal, ambiguous-close reservations and exact close attribution. PublicBroker receives transport/typed-order changes, but that does not authorize bypassing the separate local live-order gating or represent accepted submissions as fills. No order transport was invoked here.

## Confirmed inherited incoming defects

### High: failed review write is reported durable

Incoming services/heatmap_history.py save_decision_review catches storage exceptions and returns None. routes/solstice_review.py save_review nevertheless always responds with durability="durable" after calling it. Exact incoming route with a fake store returning None produced:

`{"decision_id":"missing-or-failed","state":"reviewed","saved_at":null,"durability":"durable"}`

This is a confirmed false-success path, not a hypothetical venue issue. Require a positive persisted result before claiming durability; failed storage must remain an explicit failure. Add a route-level storage-failure regression alongside test_r8_04_review_journal.py; existing success/422 tests miss this path. Review ticker/decision existence should also be bound: route currently passes only decision_id to the store, but that wider validation was not reproduced here.

### Medium: empty display is setup eligible

Exact incoming server._display_quality("OI", "vendor-supplied-greeks", []) returned state="usable", setupEligible=true, executionEligible=false. The vendor_ok/setup condition ignores the empty strikes list. An empty or wholly rejected contract population can retain the default vendor/OI labels while _display_surfaces returns no strikes. Require actual usable coverage for usable/setup eligibility while retaining the incoming readable-local-model versus executable distinction. Add empty-input and all-invalid-input cases to the display policy tests, not only valid vendor/fallback examples.

### Medium: observed-OI guard still accepts lifecycle-inferred intent

Exact incoming heatseeker.classify_nodes with `{strike:500,gamma_sign:"positive",oi_trend:"growing"}` and no source/history returns classification="real". The guard rejects a nonempty bad trend_source but permits an absent source. This affects an actual caller: routes/heatseeker.py node-classification derives growing/fading from tap lifecycle and supplies no oi_trend_source. The new doc promises observed OI; current behavior still labels tap-derived changes as real/hedge. Require explicit observed source or valid observations, and update the route to preserve unknown rather than invent OI direction. Test through that route plus the pure helper.

## Additional bounded integration risks

- **Series attribution:** incoming adapter calls resolve_series(ticker, expiry), not the actual oc.symbol root. The resolver explicitly distinguishes SPXW from SPX on the same third-Friday date, yet a SPXW contract returned under a ^SPX request is assigned the display ticker's SPX clock. Add a mixed-root same-date test before treating this as exact per-contract settlement attribution. No external venue data was fetched to establish which roots the provider returns.
- **Shared connection concurrency:** incoming recorder uses its own _RECORDER_LOCK and raw eng.conn; ingestion/query methods serialize the same underlying connection with a different _conn_lock. Background record_snapshot runs in a worker thread while several reads/writes use raw conn on the event loop. These locks do not mutually exclude each other. This is an integration risk requiring a controlled concurrent read/write regression; no race was induced against real storage here.
- **Mixed timestamp migration:** server.velocity_and_rolling sorts/limits10 rows in storage before Python normalizes legacy strings and new datetime values. Python can only reorder rows already selected. Verify mixed-type population selection before claiming newest10 across the migration.
- **No stale evaluation reuse:** the existing frozen candidate execution seal hashes modified external calculations such as gex_core/heatseeker. The pre-merge baseline must not silently count as post-merge acceptance. Preserve the seal refusal; any new evaluation requires an explicitly new freeze and unchanged honest grading denominator.

## Regression commands after conflict resolution

Use the backend virtual environment and existing offline network guard. Below are candidate bounded groups, not tests run by this reviewer. Check fixtures before running so no server lifespan/provider work starts.

`python -m pytest tests/agent tests/routes/test_agent_endpoints.py -q -p tests.offline_network -o addopts= --tb=short`

`python -m pytest tests/services/test_public_expiry_coverage.py tests/services/test_public_api_integration.py tests/services/test_public_api_partial_data.py tests/services/test_public_budget.py tests/services/test_public_budget_debit.py tests/agent/test_source_provenance.py tests/agent/test_cache_read_seam.py tests/agent/test_public_paths_invariant.py -q -p tests.offline_network -o addopts= --tb=short`

`python -m pytest tests/solstice tests/services/test_heatseeker.py tests/test_heatseeker_routes.py tests/services/test_gex_dual.py -q -p tests.offline_network -o addopts= --tb=short`

`python -m pytest tests/services/test_merged_order_regressions.py tests/services/test_journal_broker_identity.py tests/services/test_close_intents.py -q -p tests.offline_network -o addopts= --tb=short`

Known fixture migration: incoming removes server._fetch_movers_sync and routes movers through services.movers.get_movers. Local test_heatseeker_v2.install_offline_market still patches the deleted name, and the restored test_api/test_heatseeker cases reuse that helper. Update the controlled input boundary to the new implementation and preserve ranking/limit assertions; do not restore obsolete yfinance fetching merely to keep old mocks working. Existing unknown-tap/no-history expectations must also match truthful None/unknown behavior without pretending missing history is calibrated probability.

Remaining work: parent resolves conflicts, fixes or records the three confirmed incoming defects, tests the combined tree and separately reports unresolved scope. No full audit or live/model/trading readiness is certified here.

## Merged-source follow-up - 19:40 UTC

Parent reported repairs/tests for the first three findings and requested bounded reproduction of series attribution, shared storage, and review identity. Reviewer remained read-only except this report; current production callables were invoked with mocks or independent in-memory DuckDB connections. No singleton database, provider/model/broker or server lifespan was opened.

### Confirmed high: recorder rollback removes an acknowledged ingestion write

Used real heatmap_history.record_snapshot and the exact DuckDBEngine.execute_write_bulk method extracted from its class without importing/constructing the shared engine. Both used the same independent in-memory connection. A connection proxy paused the recorder immediately AFTER its real BEGIN. While that transaction was open, the main thread performed a bulk insert using the engine's separate _conn_lock. Bulk write returned1. Releasing the recorder into a controlled snapshot INSERT exception made record_snapshot issue ROLLBACK and return None. SELECT COUNT(*) from the separate ingestion probe table then returned0.

Observed result: `bulk_ack_rows=1, recorder_result=[null], remaining_ingest_rows=0`. This deterministic interleaving does not depend on simultaneous unsafe native calls: it proves transaction ownership leaks across the two unrelated locks. An unrelated acknowledged ingestion write can be rolled back by the new recorder.

Minimal robust design recommendation:

- One reentrant lock per actual connection, shared by engine and recorder. DuckDB connection objects were independently verified to work as WeakKeyDictionary keys; a small registry helper avoids retaining dead connections. Engine._conn_lock must use the SAME lock object returned to the recorder, not a new lock with the same name. Plain fake/standalone test connections need a consistent supported lookup too.
- Guard each whole synchronous recorder operation, including schema setup, reading/fetching, BEGIN through COMMIT or ROLLBACK, and nested helpers. Reentrancy is needed for record_snapshot -> ensure_tables, outcome_close_tick -> close_episodes -> record_outcome, and other nested readers/writers. The current rollback happens after leaving _RECORDER_LOCK; a new outer shared guard must still cover rollback. Protecting individual execute calls is insufficient because another writer could join the open transaction between calls.
- Whole-connection readers must also be guarded through fetchall/fetchdf; otherwise they can consume another operation's pending result. Guard engine.close as well. Never hold the thread lock across await/provider calls.
- The connection-taking heatmap_history functions are ensure_tables, recorder_status, record_capability, attach_outcomes_to_decisions, _parse_features, record_snapshot, record_wall_event, latest_wall_state, record_decision, record_outcome, record_price_path, price_paths_since, outcome_close_tick, replay_snapshot, compare_snapshots, session_manifest, list_decisions, save_decision_review. Pure formatting helpers need no lock.
- Remaining raw paths outside that module: server's window-activity SELECT using _wconn; routes/solstice.py recorder_health latest-snapshot SELECT; services/solstice_labels.py close_episodes queries; services/heatseeker_snapshots.py create_snapshot_table/bulk_insert/get_latest_snapshot/get_history/get_top_movers_from_db used by server._snapshot_chains and snapshot routes. Guard these short synchronous operations with the same helper, or route them through guarded methods. Other Solstice server/route sites generally pass the raw connection into the listed history helpers. graph_trade_service owns a different connection and is not automatically part of this demonstrated shared-engine failure.

Regression steps for the fix:

1. Create a standalone memory connection, ensure history tables, then CREATE TABLE ingest_probe(value INTEGER).
2. Give recorder AND engine the same proxy connection identity; proxy delegates all attributes, pauses after executing BEGIN via two threading.Events, and raises RuntimeError only for INSERT INTO heatmap_snapshots_v2. Binding the same proxy identity matters for a per-connection registry; do not accidentally test two artificial registry keys.
3. Start record_snapshot in one thread with a minimal SPY payload and explicit snapshot ID. Wait for the BEGIN event.
4. Start actual execute_write_bulk in a second thread for [(7,)] into ingest_probe. Assert it has not acknowledged while the recorder owns the transaction.
5. Release recorder; it fails and rolls back. Join both threads with bounded timeouts. Require recorder None, bulk acknowledgement1, and SELECT value == [(7,)]. The existing broken design acknowledges before release and ends with an empty probe table.
6. Add a concurrent-reader case that verifies read/fetch results stay associated with their own query, plus nested recorder-call cases to rule out non-reentrant deadlock. Keep all connections independent and memory-only.

### Confirmed: actual contract root is lost in series clock selection

Ran actual adapter._fetch_chain_live with a fake broker, frozen clock2026-10-16T14:00:00Z, request ticker ^SPX and actual returned symbol SPXW261016C06000000 expiring2026-10-16. The adapter returned None and logged zero contracts. The actual same-code clock called with series SPXW returned T=0.0006849315068493151, about six hours remaining. The adapter instead resolved SPX from the requested ticker/third-Friday heuristic, treating the still-open PM contract as expired.

Fix should prefer validated actual contract-series metadata/OSI root over the display ticker. Keep heuristic only when actual series is unavailable and label that limitation. Regression must include SPX and SPXW roots under the same ^SPX request on a shared third-Friday date, plus malformed root/expiry behavior. The claim here is faithful internal clock attribution; no external venue verification or rule update was performed.

### Confirmed: review writes ignore requested ticker and decision existence

Created an actual in-memory scenario_decisions_v1 SPY row with decision_id spy-real. Invoked actual merged save_review route through an APIRouter with a temporary fake engine pointing at that connection. Request ticker QQQ plus spy-real returned durable and wrote its review. QQQ plus does-not-exist also returned durable and inserted an orphan review. Actual stored reviews were [(does-not-exist, reviewed), (spy-real, reviewed)].

Schema: scenario_decisions_v1 contains decision_id and ticker but does NOT declare decision_id unique; decision_reviews_v1 is keyed only by decision_id. Suggested narrow compatibility: save_decision_review may accept optional ticker for existing low-level callers, while the route always passes its canonical requested ticker. Under the same connection lock as the INSERT, require one unambiguous existing decision for that ID with the requested ticker; reject missing, cross-ticker, or conflicting duplicate identities before writing. Prefer explicit lookup/refusal result or exception so route can distinguish404 from storage503. Do not let broad exception handling turn identity refusal into a200 durable response. Add wrong-ticker, missing-ID, duplicate-ID-across-tickers and matching-ID success/idempotence tests.

## Fresh merged-fix refutation - 20:04 UTC

Read-only production review confirms the actual connection registry lock is shared by DuckDBEngine and all previously identified history/label/snapshot operations. The outer synchronous decorator covers nested helpers, pending result fetches, and rollback; raw server window activity and Solstice health/capability reads now use guarded query_rows. Engine close is guarded. No remaining unguarded access was found in this bounded caller set. This is not a repository-wide concurrency certification.

Ran with the backend virtual environment, --noconftest, tests.offline_network, and DUCKDB_PATH=:memory: (no server/conftest import or app startup): tests/services/test_recorder_connection_lock.py plus tests/services/test_public_expiry_coverage.py: **6 passed**. This includes deterministic rollback exclusion and mixed actual SPX/SPXW roots on the same monthly date.

A separate temporary offline test used the real review route callable with an injected memory-only store. Wrong ticker, missing decision, and duplicate cross-ticker identities all refused with503 and left zero review rows. Matching lowercase ticker accepted pending/reviewed/repeated-reviewed writes, returned positive saved_at/durable, and left exactly one final reviewed row: **1 passed**. No production source or committed test files edited.

Residual limitations: identity refusal is represented as503, so callers cannot distinguish absent/conflicting identity from unavailable storage; fail-closed behavior itself is correct. Actual-root selection recognizes valid SPX/SPXW-shaped symbols but silently falls back to display-ticker inference for absent/malformed symbols; that fallback remains unlabeled and does not cross-check the date encoded in the symbol against expiration. Existing contract-root regression proves the valid-root case only. Concurrent-reader and non-weak-reference fallback cases were inspected but not separately executed in this pass.

Daily-checklist source still exposes only regime fields and maps atm_iv into iv_rank. Existing calc_gamma_flip_levels already provides key levels and hedging_flow; calc_market_regime provides expected_daily_spot_move. Restore response fields with those existing calculations, preserve missing values as unknown, expose actual ATM IV separately, and leave IV rank unknown without historical IV evidence. No deterministic strategy or risk recommendation should be invented merely to satisfy field-presence tests. Snapshot mixed-date selection is being handled by the parent and was not duplicated.

## Checklist units and constructed-query refutation - 20:13 UTC

Five temporary offline tests passed (two analytics probes, three query probes), with --noconftest, tests.offline_network, memory-only DuckDB, and no server import or production edits. These include reproductions of defects, not five assertions of overall correctness.

Hedge-unit repair verified independently at spot250, gamma0.02, OI40: total_gex50000 already represents dollar delta change for a1% move, so offsetting shares are200, not2. Up move sells200 and down buys200 under the explicitly declared call-positive model. An equal opposite put produces zero shares and direction none. Thus removing the extra0.01 factor and reversing the offsetting hedge direction are correct for this model; no actual dealer inventory or tradable prediction is established.

Two remaining missing-side issues reproduced in existing calculators: lone ATM call yields risk_reversal_25d=0 even though neither OTM wing exists (ATM defaults), and put_wall100 even though no put/negative exposure exists. Checklist should require real finite OTM call and OTM put for its quoted skew proxy, else unknown; reject absent/invalid contract side before calling the legacy skew function, which subscripts type. Wall selection should require the relevant exposure sign, with absent side and associated distance unknown. Parent notified.

Constructed queries: _esc doubles SQL apostrophes and keeps ordinary external strings in a literal. Hostile ticker/reason/note text containing quote/semicolon/DROP remained literal stored text; a quote/OR ticker did not select other rows. Fixed migration columns, fixed insert keys, and explicit int/float conversions are not demonstrated SQL-injection paths. NaN/Infinity stringification can still cause rejected writes, which is separate from executable text.

Two concrete unsafe sites remain:

- heatmap_history.list_decisions appends str(limit) directly. Passing a string containing a semicolon and DELETE to this low-level function executed that second statement against an independent probe table. The HTTP route validates limit as bounded int, so an externally reachable exploit is NOT established. Narrow fix: validate/coerce/bound the low-level argument or parameterize LIMIT; retain typed route validation.
- solstice_labels.close_episodes interpolates policy_version read from stored decision features without escaping in its outcome DELETE. Storing policy x' OR 1=1 -- with a matching censored prior outcome, then closing a longer path, deleted an unrelated decision's outcome. The real record_decision/record_outcome/close_episodes functions were used with a standalone memory connection. This is confirmed destructive second-order query behavior. An external route to create arbitrary policies was not established; current normal research policies appear generated internally. Narrow fix: parameterize the whole DELETE using decision ID, horizon, and policy (and preserve intended version matching). Add regression proving an apostrophe-containing policy cannot delete another decision's outcome.

## Final bounded confirmation - 20:17 UTC

Reviewed only the exact repairs requested by parent: parameterized outcome DELETE, validated/parameterized decision-list inputs, truthful checklist skew, signed wall selection, and corrected hedge shares. No production changes made.

Current close_episodes binds decision ID, horizon and policy as values; malicious stored policy can no longer change DELETE logic. list_decisions validates a bounded non-boolean integer and binds ticker/state/limit. Call/put walls now require positive/negative net strike exposure respectively, and missing-side distance is None. Checklist skew uses actual finite call/put wing observations from the same expiry, filters unknown side, and remains None without both wings. No new gap identified in these exact fixes.

Independent run: tests/services/test_history_query_parameters.py plus tests/routes/test_daily_checklist_truth.py **8 passed**, with --noconftest, tests.offline_network, DUCKDB_PATH=:memory:, and a tiny injected server module providing identity _sanitize only. Thus route callables/calculations/storage behavior were checked without starting the app; final server sanitation and full app integration belong to the parent's separate full suite. No provider/model/order calls or production stores touched. Previous20:13 confirmed query and missing-side defects are resolved by these specific changes, rather than erased from the evidence history. This does not certify the full application or broader financial-model assumptions.

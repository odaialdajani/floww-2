# Bounded merged order-boundary review - 2026-09-11

Reviewed at HEAD bbbff41680cc389536d4d8dc1de146803795146b.
Merge 9d5e500a parents: local 3b98ada06c756008380d0478093383b3c3fa6d32; incoming 7685a44b5e28c9d488642ff945393cc83a248899.

## Scope and provenance

Read current alpaca_client.py, routes/alpaca.py, services/order_router.py, services/close_intents.py and services/contract_validators.py; compared both merge parents. backend/schwab.py was deleted by incoming. All six scoped paths match the incoming parent; these findings are inherited incoming defects, not conflict-resolution edits. Checked immediate authentication, journal, Discord and test call paths only. This is not a total audit of the133 changed production files.

No provider/model calls or orders were sent. Reproductions used an in-memory DuckDB connection, an injected journal module collecting records in a list, and mocked broker methods; aiohttp.ClientSession raised if reached. No production journal or account was opened.

## Confirmed findings

### High: stop prices are lost between the router and paper transport

OrderRouter builds stop_price correctly at services/order_router.py:137, but submit_order forwards only limit_price to place_stock_order at201-207. AlpacaClient.place_stock_order at231-245 has no stop-price parameter and includes limit_price only for type limit.

Reproduced actual methods with a captured in-memory _post: STOP input stop_loss440 produced a transport payload with type stop and no stop_price. STOP_LIMIT input stop_loss440/limit_price445 produced type stop_limit with neither price. The old local Schwab payload retained stopPrice and its price; the incoming migration loses them. No actual venue rejection was invoked or claimed.

Regression needed: inspect final captured transport payload for STOP and STOP_LIMIT, not only _build_order_payload. Existing tests verify the intermediate payload and miss this break.

### High: a definitely unsubmitted close permanently blocks later closes

routes/alpaca.py:222 reserves a close intent before invoking the client. AlpacaClient._delete returns None immediately when disabled, before any transport. The route leaves the intent prepared with no order_id. prepare_close at services/close_intents.py:80 blocks every later attempt; reconciliation requires an order_id that does not exist.

Reproduced with a subclass whose enabled property is False and an in-memory journal: first close returns Failed to close position; next returns unresolved_close_intent; persisted state is prepared/null order_id. This is a known predispatch refusal, not an ambiguous submitted order. Preserve uncertainty for genuinely possibly-dispatched failures, but do not strand a known non-dispatch.

Regression needed: disabled/no-dispatch close creates no unresolved reservation and can later be attempted after configuration; ambiguous response still retains reservation.

### High: accepted zero-fill entries become open journal quantities

routes/alpaca.py:94-95 and154-155 journal any truthy response. Helpers record the full requested quantity with an open exit_date and no confirmed entry price. The drift query and close reservation code count these rows without requiring a confirmed entry fill.

Reproduced place_order with status accepted and filled_qty0: helper emitted a new open quantity2 seed. This represents unfilled requested shares as an open journal quantity and can inflate close-target quantity. The option sibling uses the same pattern. Existing test_alpaca_paper explicitly expects a seed after accepted; this needs an honest pending convention or confirmed-fill gating, not a claim that test success validates a fill.

Regression needed: accepted/zero fill, partial fill and full confirmed fill for both stock/option route siblings; no guessed fill price or duplicate quantity.

### Medium, currently unused helper: nonfinite volume/open interest passes validation

contract_validators.py:73-76 checks numeric type and negativity but not finiteness for volume/open interest. Reproduced validate_chain_row returning (True,None) for NaN volume and infinite open interest. No production caller of this helper was found in the bounded search, so no active ingress impact is claimed.

Regression needed: NaN and positive/negative infinity in both fields reject without raising; valid finite zero stays allowed.

## Boundaries that remained intact

The actual default venue is hardcoded paper-api.alpaca.markets. Deleting the old Schwab live gate did not redirect current orders to a live URL. No current production import of the deleted SchwabTokenManager was found. Global server mutation authentication calls verify_api_key; Alpaca mutation paths are not public exceptions. Existing account/position/order reads retain explicit key dependencies. Public brokerage gating was not redundantly audited.

Normal router MARKET calls remain rejected unless the explicit per-call opt-in is used. Stable client IDs and venue recovery remain present. No new permission bypass was confirmed within this scope.

## Follow-up authorization and checkpoint

Parent explicitly authorized fixing these four confirmed incoming defects with failing regressions first, fully mocked transport and unchanged paper/auth/live boundaries. Own affected production modules and focused tests only; do not revert others' work. Inspect pending-journal conventions before choosing fill handling; report a material lifecycle ambiguity rather than silently designing a new order lifecycle.

Before these fixes, parent also requested a short independent review of services/ingestion_pipeline.py and tests/services/test_ingestion_write_failures.py. Current normal graceful stop waits for the writer with shield then final-drains; each failed batch increments unconfirmed_write_rows and other types continue, with no retries. A canceled stop may exit before its final drain; determine whether this is a new regression or an existing cancellation limitation and test safely. No ingestion source edits are currently assigned.

Current agent/window: /root/final_small_review; 01a09277-89ba-7311-9d02-b6419de870f7. Latest parent fix authorization received22:47:18UTC, no exposed item ID. No order fixes have been made yet. Existing changes by other agents must be preserved.


## Fixes implemented and bounded proof - 22:56 UTC

Parent authorized the four repairs and the same accepted-as-filled defect in the router and Discord sibling. Source is now frozen for independent parent review; no commit or full-suite run was made by this agent.

- Actual router -> AlpacaClient -> captured POST now retains stop_price and both stop/limit prices. Default paper URL, authentication and per-call market opt-in remain unchanged.
- Disabled close is refused before preparing any journal reservation. A later enabled call can submit. An ambiguous attempted close still retains its reservation and blocks a duplicate.
- Alpaca stock/option responses preserve raw venue fill fields. Shared services/entry_fills.py requires attributable order identity, exact symbol/side/requested quantity, finite nonnegative executed quantity no larger than requested, and a finite positive actual average fill price. Zero/unknown fills create no holding. Positive partial fills record only their confirmed quantity and price; full fills likewise use actual venue values. Responses expose journal_status and unfilled_qty.
- Router position totals use confirmed quantity, never requested quantity. Duplicate cached submissions do not increment twice.
- Stock/option routes and Discord share one confirmed-entry journal helper. It holds the existing connection lock across broker-order-ID lookup and insertion. Same order/same cumulative execution adds no second row, including equivalent quantity strings. Changed cumulative totals or attribution do not silently overwrite an existing holding; they return reconciliation_required. A refetch with a different order ID is rejected.
- Chain volume/open-interest checks reject NaN and either infinity; valid zero remains allowed.

Focused production-path regression first run: 19 failed / 4 passed before source edits. The Discord sibling separately reproduced 3 failures before its fix. Subsequent refutation tests exposed boolean fill prices and numeric-string dedupe equivalence, both fixed; a distinct-order Discord readback was reproduced and fixed too. Old tests that treated an accepted submission as a fill were changed to assert no holding or provide a complete confirmed-fill fixture, not removed/skipped.

Final command (backend Python 3.11 environment):

`python -m pytest tests/services/test_merged_order_regressions.py tests/services/test_alpaca_paper.py tests/services/test_order_router.py tests/services/test_order_router_gate.py tests/services/test_close_intents.py tests/services/test_discord_ops.py tests/services/test_discord_g3_paper_loop.py tests/routes/test_reconcile_close.py tests/routes/test_position_drift.py tests/test_contract_validators.py -q --noconftest -o addopts= --tb=line`

Result: 187 passed, 0 skipped, 4.56 seconds. Two unrelated warnings: pytest ignored .hypothesis directory and Python audioop deprecation. New regression file contains34 cases. All new order tests refuse aiohttp.ClientSession and use in-memory DuckDB or mocked broker methods. No live order, venue request, account access, paid model call or production-journal access was performed.

## Remaining scope limits

This bounded patch does not add an eventual entry-order reconciliation worker or a full pending-order lifecycle. A partial entry captured now stays at its confirmed quantity until explicitly reconciled; a changed later snapshot returns reconciliation_required instead of duplicating or guessing. Router in-memory positions also do not independently track later asynchronous fills. Existing historical journal rows that were incorrectly created from submissions are not silently migrated/deleted: venue evidence is needed to repair those rows safely. These limitations must remain in the parent unfinished-work report.

The direct entry routes previously had no durable pending-order record, and none was claimed as implemented here. Existing journal composite keys can reject distinct orders with exactly matching asset/action/time; such storage failure surfaces journal_unavailable instead of a false success, and is not a new lifecycle implementation.

## Independent ingestion review

Read the modified ingestion source and new failure tests; independently ran all12 write-failure tests successfully. Per-type errors now count unconfirmed_write_rows and still attempt the other types. Normal stop shields the active writer, waits for its outcome, then drains later arrivals. No hidden retry or claim of exactly-once persistence was added. Caller cancellation can still interrupt stop before final drain; this is a broader pre-existing shutdown-cancellation limitation, not a newly introduced successful-stop failure. No ingestion source or tests were edited by this reviewer.

## Independent review reopen and repairs - 23:09 UTC

The independent reviewer reproduced three additional defects after the first source freeze. These were repaired rather than accepted as scope limits. This section supersedes the earlier statement that same-time distinct-order key collisions remained open.

1. The router now uses the actual outgoing canonical symbol and side for its position totals. Input spy/BUY with a confirmed2share buy records SPY:+2, never spy:-2.
2. Journal identity now carries optional broker_order_id. New broker rows use alpaca-order:<venue-id>; legacy rows retain empty identity. The primary key includes that field, so distinct venue orders at one genuine fill timestamp both persist without altering that timestamp. The old table is rebuilt inside one transaction, copying all old columns verbatim; failure rolls back. No production journal migration was run during this task. Read responses export broker_order_id for the parent-owned TradeJournal merge guard.
3. Existing positive execution followed by the same order's zero/unknown snapshot returns reconciliation_required. It cannot revert to pending or erase known holdings.

Close-key compatibility: legacy keys retain six parts and address only empty-identity legacy rows. New keys add a seventh URL-encoded broker identity. Exact-row close queries and durable close reservations carry this identity. Reservations saved before the extension default the absent identity to empty and cannot acquire a new same-time broker fill. The key helper also preserves numeric zero; historical equity keys that encoded zero as empty remain accepted.

Three new reproductions failed first on the independent findings. Six additional tests cover legacy migration preserving all values, repeat initialization, failure rollback preserving old data, distinct same-time fills closing independently, two-target close exactly once, legacy reservation isolation, and file-backed migration/reopen with a legacy row plus two distinct real-timestamp fills. Only temporary/in-memory stores were used.

Final focused group: 215 passed, 0 skipped, 5.00 seconds across merged-order regressions, broker identity migration, journal store/closeout/lifecycle, Alpaca transport/routes, router/default market gate, close intents, Discord, drift/reconciliation and contract validators. After tightening one exception expectation for lint, all6 identity tests passed again. Ruff passed for all owned source/tests. Source frozen for the independent reviewer; no full suite or commit from this agent.

Still not claimed: an asynchronous entry reconciliation worker or reconciliation of old historically guessed holdings. Those are distinct from the three now-fixed defects above.

Final timestamp honesty refinement23:11: missing broker filled_at now remains empty/unknown, never replaced by current wall-clock time. Confirmed partial quantity and price still persist under their stable broker identity. A new failing regression proved the previous fallback invented a timestamp; it now passes. Updated focused total216 passed, 0 skipped, 5.00 seconds; identity tests7. Ruff passed. Independent frontend reviewer was notified of the final source freeze.

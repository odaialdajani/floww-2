# Independent journal identity review

Assignment received 2026-09-11 23:09 UTC: refute latest journal migration, rollback/restart behavior, legacy key compatibility, separate broker identities and frontend read alignment. Production data, brokers and providers must remain untouched. Source changes require author coordination.

Files read: journal_store.py, close_intents.py, entry_fills.py, order_router.py relevant call sites, TradeJournal.jsx and identity tests. No graph indexes are present. Existing migration tests cover preservation, deliberate failed-copy rollback, distinct same-time fills, legacy reservation isolation and reopen.

## Confirmed finding: cached broker rows hide newer reconciled closes

Severity: medium. TradeJournal's loadServer merge filters out all matching cached rows instead of refreshing broker-owned values. The new broker identity comparison correctly keeps separate orders and manual tickets apart, but a matching old open row still suppresses a newer closed server row. Thus a confirmed close can remain shown as open with stale totals after reload/focus.

Mounted reproduction: seed localStorage with one open SPY equity row carrying broker_order_id=alpaca-order:one. Mock the server response with the same identity and newer updated_at, exit_price=501 and an exit timestamp. Mount TradeJournal and select Closed. The screen says No trades match filters. The added TradeJournal.serverReload.test.jsx expects the SPY row and failed on the unchanged production component (23:11 UTC). No real endpoint was called. Parent owns the production component and was notified to repair; this review has not modified it.

The merge pattern predates the identity patch but directly affects the new reconciliation result. The repair should refresh matching broker-owned execution fields while retaining local/manual rules and separate order identities. This review does not broaden into unrelated journal editing or paper accounting.

## Bounded backend evidence

At 23:11 UTC independently ran `.venv/Scripts/python.exe -m pytest tests/services/test_journal_broker_identity.py -q --noconftest -p tests.offline_network`: **7 passed**, 0 failures. One Hypothesis collection warning; no external attempt. All stores were in-memory or a pytest-owned temporary file.

- Migrating the prior six-column primary key preserves all prior field values, including timestamps, and gives legacy rows the empty broker identity. Reinitialization is idempotent.
- A forced copy failure caused by an extra legacy column rolls the migration back without dropping rows or adding the new identity column. This proves failure preservation, not support for arbitrary custom columns: unsupported extra columns still stop migration.
- Two fills at the same timestamp persist separately; the seven-part close key updates only the chosen fill. Six-part keys target only the empty-identity legacy row.
- A pre-change close reservation lacking broker identity applies to its legacy row only; a newly inserted same-time broker fill stays open.
- Closing a reservation containing two known fills updates both once. Repeated application does not close them twice.
- A migrated file reopens with all three rows, identities and timestamps unchanged.
- Latest source refinement leaves missing broker filled_at unknown (empty entry_date), rather than stamping a fabricated current time; its new test passes independently.

A separate direct isolated-store probe inserted two broker IDs containing literal delimiter/percent characters plus one legacy row. The URL-quoted key retained exactly seven parts and closing it changed only the intended row. The actual DuckDB constraint contains exactly the seven expected columns with broker_order_id last. Probe passed.

No new backend defect was reproduced in this bounded review. This is not a claim that the full paper lifecycle or all historical data are verified. No production journal, broker, provider, model, environment setting or order was touched. Only this report and the mounted regression test were added; no commit made.

## Authorized frontend repair - 23:15 UTC

Parent delegated TradeJournal.jsx and related checks after the failing reproduction. Matching broker rows now refresh only execution/provenance fields from a strictly newer saved server record. Local notes, tags, setup, levels and stable card ID remain. Manual/legacy merge behavior and separate-order identity remain unchanged. A separate saved broker timestamp lets a later local annotation edit coexist with an earlier server close update. Naive DuckDB timestamps are compared as UTC. Older, equal, missing or malformed server timestamps cannot replace saved execution values.

Independent backend author suggested the optional-time sibling: identical broker identity with previously unknown entry_date compared unequal after the server supplied a real time. A new comparison test failed before repair. Broker ID now establishes equality directly; optional execution metadata no longer creates a second holding.

Final bounded run after source changes: **5 suites, 61 passed**, including mounted cached-open to server-closed reload, strict timestamp ordering, known-time update, local annotation/card retention, manual-row retention, repeated reads, separate broker identities, existing trade math, entry and journal plans. Used CI=true with --watch=false --runInBand --forceExit and explicit five paths. Force-exit was selected because the initial failing craco invocation kept its process open after reporting its result; that owned test process was stopped. No application process was touched. Whitespace check passed. Parent retains full combined frontend build and actual desktop verification.

Owned frontend files at handoff: TradeJournal.jsx, TradeJournal.merge.test.js, TradeJournal.serverReload.test.jsx. No commit made. The earlier confirmed frontend finding is repaired under bounded tests; independent helper refutation has been requested from the backend author.

## Independent refutation and follow-up repair - 23:20 UTC

The independent reviewer disproved the initial helper in two cases: JavaScript millisecond date parsing treated DuckDB .123100 and .123900 as equal, hiding a newer close; an older cached broker row without the dedicated clock could have a later local edit timestamp that hid the real close forever. These override the earlier broad ordering claim.

Both new regression checks failed before repair (**2 failed, 5 passed** in the reload suite). The timestamp comparator now keeps the complete six-digit DuckDB fraction as integer microseconds separately from whole-second timezone parsing. Only the dedicated broker clock establishes prior execution ordering. If that clock is absent, the first valid server record establishes it while retaining local annotations. The older/equal/missing/malformed server test uses an actual dedicated broker clock and remains passing.

After the follow-up: **5 suites, 63 passed** using the same five explicitly scoped journal paths at 23:20 UTC. The exact two reviewer probes were requested again against frozen source. Parent must use this newer source for final build/combined checks; the earlier 61-test result predates these final corrections. No commit or application process action performed.

## Independent frontend helper refutation - 23:19 UTC

Read-only review by the backend author, bounded to journalKeysEqual/mergeJournalRows, the two related test files, and the local save timestamp. Executed the current pure helper source (extracted verbatim before TradeForm, only removing export keywords) in Node vm; no network or application session was used. No source/test changes by this reviewer.

Two concrete defects remain:

1. **Microsecond ordering is lost.** Local broker updated_at=2026-09-11 10:00:00.123100 and server close updated_at=2026-09-11 10:00:00.123900 both produce Date.parse value1789120800123. The incomingTime<=cachedTime branch rejects the newer confirmed close. Actual merged row retains exit_date='' and exit_price=''. DuckDB stores sub-millisecond timestamps, so this is a real representable event order, not an invalid-time probe.

2. **Old cached local edit time can permanently suppress the server close.** For an existing broker row without the newly introduced _broker_updated_at marker, saveTrade writes local updated_at (TradeJournal.jsx335). Reproduced local updated_at=2026-09-11T12:00:00Z with no broker clock, followed by a same-identity server close updated_at=2026-09-11 11:00:00. The helper falls back to the local edit time, treats the server as older, and leaves exit_date='' and exit_price=''. No broker marker is established, so the same close is rejected again on later reloads. The existing annotation test includes a known broker marker and does not cover migration of prior cached rows.

Broker identity comparisons, notes/tags/setup/levels preservation and manual-row behavior were read but no additional finding is claimed. The findings above are independent of the completed backend broker identity migration. Parent and frontend author were notified for bounded repairs; this reviewer made no source edits and ran no full suite.

## Exact independent recheck - 23:22 UTC

Re-ran the same two pure-helper reproductions against the frozen repaired TradeJournal.jsx, with no source edits and no scope expansion. Both now pass: the same-millisecond later close replaces the cached open fields, and a legacy cached row with only the later local edit clock accepts the confirmed server close while preserving its local ID and notes. The helper records a dedicated broker timestamp in each result. The exact timestamp values123100 and123900 now parse to1789120800123100 and1789120800123900 microseconds, correctly separated by800 microseconds. Both prior findings are resolved in this bounded independent recheck. No full-suite or live-app claim is made by this reviewer.

## Independent stock-vs-option money recheck - 23:27 UTC

Read only: parent corrected tradePnl's equity contract factor and form reuse after the actual desktop showed a2share500->501 gain as200 dollars. Independently ran only tradeMath.test.js:45 passed,0failures,0.519seconds. Also executed current helper source for8 direct checks: long stock+2, short stock-2, fractional long-0.50, fractional short+0.50, long call+200, short call-200, long put-200, short put+200; all matched exact arithmetic.

Bounded sibling scan confirmed journal form, cards, totals, sorting, CSV and TradeAnalytics all use shared tradePnl. Remaining100 factors in those two journal surfaces are percentage/chart scaling, not share-dollar conversion. Option-specific notional and strategy helpers retain their100-share convention. Equity is present in the form type list. No new defect in the requested money-factor repair was found. No source edits or full suite from this reviewer.

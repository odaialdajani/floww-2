# Research comparison history-input review - 2026-09-26

**PASS for the isolated synthetic history-preparation helper under the reviewed tests and probes.** Reproduced validation, ownership-expiry and partial-write defects are fixed. This review does not certify durable MongoDB recovery, research answers, model use, shared-turn budget enforcement or release readiness.

## Scope and identities

The reviewer owns only this report and `output/research-history-review-*` probes. No production or proposal files were edited by the reviewer. The five prospective synthetic history recipes were exercised through actual `ResearchReads.snapshot`, `AgentRepository.save_anchor`, and `history_facts` with a mock MongoDB transport. No completed research turn, answer, model/provider call or answer report was created/read. The source proposal remains unchanged.

| Reviewed file | SHA256 |
| --- | --- |
| backend/scripts/research_comparison_history.py | 5c5d6648f85f2a4b74bf856ed2c0c0f2c2474d293458dbab3c040fb435eeaca1 |
| backend/tests/agent/test_comparison_history.py | c681bd5a70c717d1001d3a35dcdf322526322321664ecafef84f617c980e0ead |
| .planning/eval/research-fresh-comparison-proposal-20260926-v3.json | 305a42af3a8d86ed8e39ad314a99c592ad2fb57ccab53faf575e507e3aa71c2b |

At 23:32 UTC the reviewer ran `.venv/Scripts/python.exe -m pytest tests/agent/test_comparison_history.py -q --disable-warnings` from `backend`: **19 passed**, 27 existing warnings. The independent probe is `output/research-history-review-probe.py`; final results are in `output/research-history-review-final/results.json`, with an additional rollback-failure check in `output/research-history-review-cleanup/results.json`. Both final probes confirmed unchanged reviewed source bytes and zero network attempts during fixture operations. Windows event-loop setup occurred before the network guard because it creates an internal loopback socket pair.

## Independent normal-path results

The five cases create seven actual saved anchors in their separate mock-backed repositories, with zero research-turn records. The inputs remain unchanged. Snapshot prices, source identity, source time, contract count and independent coverage digest are checked against raw source fields before any save. The stored snapshot is reread and compared exactly before a successful receipt is returned.

| Declared case | Verified result |
| --- | --- |
| owned_price_change | Earlier IWM price 100 and current price 102 produce 2 USD change with both source parents. |
| history_changed_selection | Prior four-contract/two-expiry coverage differs from current two-contract/one-expiry coverage; no price change is returned. The note identifies the mismatch. |
| other_owner_history | The asking owner cannot use the separately owned prior. No price value or source time is disclosed in the absence note. |
| late_snapshot_not_close | The intraday prior does not satisfy the exact 2026-09-28T20:00:00Z closing observation; no close-based change is returned. |
| three_ticker_history_budget | QQQ, IWM and DIA each have compatible prepared prior/current prices 100/102 and a 2 USD raw history change. This is preparation/read proof only, not the later shared question-budget result. |

An unrelated owner receives no history facts for every case. Anchor insertion timestamps fall between actual wall-clock instants captured around preparation; synthetic snapshot capture timestamps remain September 28. Session/storage expiry clocks were not replaced by the hypothetical evidence clock.

Each prior-preparation receipt reports its own read activity and explicitly excludes that activity from a research turn's budget. The three-ticker preparation records two reserved/started reads per ticker, with each budget closed. Read-budget context is restored after normal operation and injected failures. These six preparation reads are not represented as a single question's complete capability accounting.

## Reproduced findings and fixes

1. **Missing history rows silently reduce coverage - fixed.** Removing one ticker initially saved two anchors for the three-ticker case, and empty history returned an empty success list. Final validation requires the exact nonempty requested ticker set and the count appropriate to the declared variant. Both malformed inputs now fail before any save.
2. **Uncaptured chain/IV observations can enter prior history - fixed.** Future chain or IV times initially passed because validation covered only the spot observation/receipt. Final checks bound all recognized observations and receipts to each raw record's capture receipt and enforce chain/spot ordering. Independent tests reject a next-day observation and an observation at 14:26 that is before the question clock but after the prior's 14:25:01 capture. No anchors remain.
3. **Expired owners can be seeded while expiry cleanup lags - fixed.** A normal mock expiry test auto-deleted the session and hid this issue. With the expiry index removed to model delayed deletion, the expired session initially received three anchors. Final session lookup explicitly requires expiry later than real current time; the still-present expired session is now refused before writing.
4. **Partial storage failure leaves a usable-looking subset - fixed with scoped rollback.** An injected second-write failure initially left the first anchor. Final code tracks attempted owner/snapshot identities before each write and deletes only those anchors if saving or round-trip confirmation fails. The independent probe now leaves zero anchors. The focused test also covers a write that succeeds before its acknowledgment raises, and verifies that an unrelated owner's existing record remains intact.
5. **Recipe metadata can disagree with the prepared input - fixed.** The late variant initially accepted the generic observation kind, and an already-inserted declaration was ignored. Final validation requires the variant's exact observation kind and `store_inserted=false`. Both are independently refused before saving.

The independent malformed-input set contains ten cases: missing ticker, empty history, future chain observation, future IV observation, prior observation after capture, expired owner with and without cleanup, invalid second ticker, wrong late-anchor kind, and claimed prior insertion. All ten now raise with zero anchors and zero research turns.

All source snapshots are prepared before the first save: a deliberately failing second snapshot preparation leaves zero records. A deliberately failing rollback produces an explicit cleanup-unconfirmed error and no success receipt; one partial anchor remains in that simulated unavailable store. The caller must discard that isolated preparation, not continue from it or count it passed.

## Boundaries

This reviewer used mock-backed storage for adversarial failure injection. A separately recorded root-run proof with real MongoDB and a fresh-process reopen is required for durable-storage claims; the earlier root proof is not treated as evidence for the final helper hash without its rerun. No such real-storage result is claimed here.

The caller must provide an isolated repository/session for each preparation and exclude concurrent unrelated writes to the same owner. The helper verifies an empty owner and an active session; it is not a transactional lock around competing writers. Rollback targets only attempted anchors. Newly created separate-owner session records may remain until the isolated store is discarded or normal session expiry occurs. If rollback cannot be confirmed, discard the isolated store and all owner identities created for that preparation.

The helper does not fabricate completed answers and does not establish later question admission, actual multi-ticker read ordering/denials, candidate interpretation, saved-answer recovery, browser timing, monetary cost, real-market freshness or trading success. Historical source observations and synthetic timestamps remain separate from real session and storage clocks.

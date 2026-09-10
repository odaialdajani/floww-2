# Agent 2 — backend repair owner

Read this package's shared protocol and Agent 1's current card. No card means
read-only discovery and a checkpoint, not self-admission. Own no frontend files,
frozen model paths, shared control docs or merges.

First admitted repair candidate: PR58, starting from its fetched remote head
(not stale local b9d611a). Inspect routes/alpaca.py, services/journal_store.py,
alpaca_client.py and tests/routes/test_reconcile_close.py/test_position_drift.py.
Resolve exact paths against your assigned worktree.

Reproduce wrong-symbol filled order closing another symbol's journal card.
Required safety cases: mismatched/missing order identity, opening order masquerading
as close, wrong side, partial quantity, duplicate reconciliation after a new card
opens, old close replay, option/equity same-underlying separation, nonfinite price,
venue failure versus empty position. Unknown attribution must not mutate journal.
Use real in-memory journal storage and mocked venue transport, not mocked journal
success. Persist close intent/target identity only under an explicit reviewed
schema/migration contract; escalate that architectural decision if absent.
Do not paper over the defect with only a symbol check.

After RED/GREEN and neighboring suites: commit only leased files, ordinary push,
write exact-head receipt and hand off to Agent 4. Do not self-review or self-merge.
Next cards, one at a time: PR62 documentation consistency, PR63 registry truth.
Pinned means a specific executable assertion detects drift, not file existence;
calibrated requires empirical evidence. Never change numeric weights to fit copy.

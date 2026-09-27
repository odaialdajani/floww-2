# Final bounded preparation review - 2026-09-26 22:36 UTC

**Current verdict:** the reproduced quote-mutation and protected-exit capacity defects below are resolved in the reviewed source. No additional blocker was found within this bounded, unmounted preparation slice after the final checks. This is not paper release/admission approval or complete options lifecycle verification. Historical findings and original failure output remain below.

The reviewer independently ran Python 3.11 with -B and unittest discovery for test_agent_paper_*.py. All 28 focused tests passed. Additional in-memory probes checked original failures, final archival, precision refusal and clock rollback. The 22:34 real-Mongo report lists 15 passing controller checks; I inspected it but did not rerun its persistent-store work. That report predates the final clock-watermark change and alone does not certify that change.

## Final fixes checked

- Quote input comes from the detached command after awaits. Mutating the caller quote during receipt lookup still saves ask 2.00 and applies the original 2.05 configured fill.
- Each structure prepays 12 event credits, one close-order slot and eight new quote-row slots. Close staging transfers capacity: credits fall from 12 to 11. At the maximum valid pending count the close fits. At the maximum valid ordinary quote-row count, a reserved close can insert its row without consuming other protected slots.
- Only one retained close may exist per structure, including terminal closes. Replenishment refuses while any close remains retained and while history is pending. This supersedes the interim two-close/16-credit design, which could accumulate more obligations than flat replenishment funded. An independently exercised eight-fill close, after opening archival, leaves two event credits before final close archival; the final archive removes the empty structure budget.
- Fresh-operation semantic duplicates refuse and direct callers to the original persisted receipt. Accepted original-operation retries return that receipt. No-fill None/False is explicitly an unaccepted/uncommitted request and cannot be advertised as a saved event. This removes the false accepted-alias ambiguity.
- Derived-value arithmetic traps inexact results. A fee of 1e-200 combined with 1e72 notional now refuses when 256-digit arithmetic cannot retain it, instead of silently losing the fee.
- A persisted checked-at time prevents backward service-clock movement during staging, fills or replenishment. Before the fix, my advance-by-301-seconds/prune/rollback probe filled two orders from a quote displaying one unit. The same sequence now refuses. Existing accepted-operation receipt retrieval remains nonmutating.

Final independent probe results:

```json
{
  "close_budget": {
    "before": 12,
    "after_staging": 11,
    "existing_state_fits": true,
    "close_at_capacity_refused": false
  },
  "full_quote_ledger_refuses_close": false,
  "quote_mutation": {
    "saved_command_ask": "2.00",
    "applied_fill_price": "2.05"
  }
}
{
  "bounded_close": {
    "retained_close_replenishment_refused": true,
    "credits_before_final_archive": 2,
    "positions_after_final_archive": 0,
    "exit_budgets_after_final_archive": 0
  },
  "derived_fee_precision": {
    "refused": true,
    "reason": "Paper arithmetic exceeds exact supported precision"
  },
  "backward_clock_after_quote_prune": {
    "refused": true,
    "reason": "Paper clock moved backwards; retain saved quote consumption"
  }
}
```

The quote-cap probe uses the maximum valid ordinary ledger size: 256 minus protected quote rows. The former 256-plus-reserves state is correctly no longer admissible. Probes use synthetic state and in-memory stand-ins; they do not certify persistence.

## Scope that remains open

No mounted action route or production admission composition exists. Research acceptance, verified proposals/contracts, human confirmation and risk checks, exchange sessions, expiry/exercise/assignment/deliveries, corporate actions, dividends, multi-leg execution and operational release gates remain separate. Budgets guarantee a finite recorded close attempt, not successful liquidity or unlimited retries during unavailable history storage. Replenishment must preserve actual order/quote/document space. Frozen-account reopening/rebinding stays behind the separate recovery contract.

The trusted admission callback is a future integration point, not evidence that real-world gates passed. The reviewer made no provider/model calls, broker orders, source edits or persistent-store mutations.

Final reviewed SHA-256:
- backend/services/agent/paper/execution.py: d38c3ca7cfe1369a5ab0eb8a5b850f366c84fa7d71fbac1fea6883daf8b082c9
- backend/services/agent/paper/service.py: 541f452ea58c88b3a829e13b90041ad431b881b18888fadb8771c7c37808992f
- backend/services/agent/paper/accounting.py: 0ea3b327b1b9e6f7f8e6304de45f353a281aa7f3afdc932f9c8a609f0436a8c7
- tests/test_agent_paper_execution.py: 8cf36d1dd0fc2a9fdc95048c1ad2c90f6195a811403337fce260d5a15d50f54d
- tests/test_agent_paper_arithmetic.py: 80a8def25e2d8bbce5493c4ee585a610dc1bf7f02d02568a7f0c6e7d26c8c33f

---

# Independent prepared paper execution review

Reviewed 2026-09-26 22:24 UTC. Scope: execution.py, service.py, focused pure-transition tests and repository receipt/save behavior. This is preparation only; no production composition, provider/order calls, or paper admission approval. Reviewer changed only this report.

## Verdict

The prepared code earns useful invariants: account-version writes prevent competing transitions from both winning; source quote identity prevents the same order counting that quote twice; displayed size is shared between orders; terminal retirement requires projected history; separate structures sharing a contract keep separate holdings. Three reproduced defects and one related capacity omission must be resolved before claiming bounded exit availability or frozen-input correctness.

## Findings

1. **High - quoted economics can change after command identity is frozen.** PreparedPaperService.quote constructs a detached command, awaits receipt/read calls, then passes the original caller-owned quote dictionary into fill_order. An intervening mutation changes the actual price while the saved command digest still represents the earlier quote. My in-memory service probe saved command ask 2.00 but applied a 1.85 fill from a mutated ask 1.80 plus the configured 0.05 adverse movement. Use command['quote'] and command['order_id'] consistently after freezing. Add an awaited mutation test that asserts both economics and saved command remain the original values. The stage path correctly uses its detached command fields; preserve that pattern.

2. **High - held-position exit reservation cannot fund staging the exit.** recovery_events currently retains only two events per held structure. Staging a close creates a working order with eight possible partial fills plus cancellation, increasing its reserve from 2 to 11, while staging itself appends another event. A valid account sitting at its normal admission limit therefore cannot stage the close promised by those two reserved events. Reproduced using actual transition functions and repository._size: the existing state fit; the close was refused. Reserve a declared bounded close attempt before admitting the original exposure, then transfer that budget from held-position obligation to active close rather than creating unreserved obligations during reduction. Cover staging, bounded partial fills, remainder cancellation and any required terminal bookkeeping. Define what remains guaranteed after a partly filled cancelled close; no finite reserve can promise unlimited failed exit attempts without history drainage.

3. **High - a separate quote-ledger cap blocks closing fills.** A current source quote absent from a full 256-entry recent-quote ledger is refused even for a closing order with reserved event/document space. Reproduced with an otherwise valid staged close. The quote ledger cannot safely discard eligible consumed liquidity, because that would permit reuse. Reserve quote slots for outstanding reduction obligations or define a separate bounded reduction allocation while keeping shared quote consumption authoritative. Prove the guarantee at the actual ledger cap and while old quotes remain eligible; waiting up to five minutes for expiry is not immediate exit availability.

4. **Medium - the order-count cap needs the same reduction guarantee.** MAX_ORDERS counts terminal orders retained for archival as well as working orders. All staging, including closes, refuses at 24. Terminal archival requires projection and another saved transition. Therefore a blocked projector can strand available economic holdings behind the order cap even when storage bytes were reserved. Reserve close-order slots or restrict entries so existing positions retain a defined close path under this count limit. Do not silently archive unprojected records to make space. This finding follows directly from stage_order/archive behavior; it was not separately reproduced in a real store.

## Important limits, not newly discovered defects

The trusted admission callback is explicitly absent from production composition and does not establish research, proposal, human confirmation, risk, market hours or lifecycle acceptance. Quotes still require trusted provider provenance; syntactic source IDs cannot prove an external feed is genuine. Price/size/fee/limit tests do not establish expiry, assignment, settlement, corporate actions or dividend handling.

A closing fill whose fees exceed proceeds can reduce cash; do not confuse recording an obligation with admitting new exposure. The eventual risk policy must account for such costs and outstanding reservations. Lifecycle deliveries remain unimplemented.

Unfilled quote attempts and no-op cancellation results return without a new durable event. That is safe against duplicated cash, but it does not establish a durable audit trail of every unfilled/rejected attempt. Define that contract explicitly if required by the release gate.

## Evidence

Read the complete source and ten focused tests. Executed direct Python 3.11 imports using hidden processes, no bytecode output, existing synthetic test fixtures and in-memory stand-ins. No persistent database or source files changed. These probes reproduce logic defects; they are not concurrency or durability certification. The parent is preparing the real-store controller proof.

```json
{
  "close_budget": {
    "before": 2,
    "after_staging": 11,
    "existing_state_fits": true,
    "close_at_capacity_refused": true
  },
  "full_quote_ledger_refuses_close": true,
  "quote_mutation": {
    "saved_command_ask": "2.00",
    "applied_fill_price": "1.85"
  }
}
```

Required additions: frozen quote across awaited work; close staging at maximum admitted pending/document/order/quote capacity; budget transfer over partial close, cancellation and retry; same-source-quote races on one and two orders; fill-versus-cancel with fresh reload; crash after committed fill before response/project; archived late-fill refusal; and exact cash/holdings agreement after restart. Existing pure tests cover several sequential equivalents, not these complete storage transitions.

Reviewed source SHA-256:
- backend/services/agent/paper/execution.py: 8fb10e0b41f0e8f3d484f784de5c5099279a7b115783048964134df7891f7832
- backend/services/agent/paper/service.py: 69170105320d144b6542fd6c1812ceca8bdac5bd05af05874da75c5491e45a5a
- tests/test_agent_paper_execution.py: cf286ca8a4df73a3b9bb5ba8c25762c2774b9a80ea1b78a0e498f39556d1fb57


## Minimum bounded reduction-slot strategy - 22:25 UTC

Reserve one close-order slot per prospective structure at entry, including working opening orders. Require retained orders plus unused protected close slots to stay within the order cap. Permit at most one unarchived close order per structure. Close staging converts its protected slot into an actual order; terminal cancellation/fill retains that slot until verified projection and committed archival. A remaining position can obtain another attempt only after safe recycling.

Reserve up to eight future quote rows per protected close attempt. Entry and ordinary quote insertion must preserve eligible-ledger rows plus unspent protected quote slots within the quote cap. A reduction that creates a new quote row consumes its protected slot; reuse of an existing shared row consumes no additional row. Projection alone cannot replenish this capacity: eligible quote consumption must survive until safe source-quote expiry, otherwise displayed size can be reused. Replenish from actual remaining row capacity only.

Use a separate structure-obligation record for event credits so deleting the last holding cannot erase the still-required terminal-order archival credit. Eleven event credits conservatively cover one stage, up to eight fills, cancellation and archival; transfer rather than double-count position and active-order credits. Credits spent on a cancelled attempt are not magically refunded. Replenishment requires durable projection and available real capacity. This guarantees the ability to record a bounded attempt, not a successful executable exit or unlimited retries during unavailable history storage. These are design recommendations; no implementation of them was reviewed in this artifact yet.

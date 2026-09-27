# Independent incoming-order review

2026-09-11 22:59 UTC. Read-only source review plus fully mocked/local probes. No broker, provider, model or real order calls; no source edits. Reviewed entry_fills, routes/alpaca, order_router, alpaca_client, Discord shared-entry caller and merged-order regression tests while author retained ownership.

## Confirmed findings sent to author and parent

1. **Wrong signed/ticker position on accepted mixed-case input.** submit_order builds and dispatches normalized payload SPY/buy for intent ticker="spy", side="BUY", qty=2. Broker returns correctly attributed filled_qty=2 at500. The current tracker update reads the raw intent instead, resulting in {"spy": -2.0}. Use the canonical payload symbol/side for tracking. Local probe used only AsyncMock broker methods; no dispatch occurred.
2. **Distinct broker orders can collide in journal primary key.** journal_confirmed_entry deduplicates by ckey="alpaca-order:"+id, but INSERT still uses the legacy primary key ticker/type/action/strike/expiry/entry_date. Two genuine distinct order IDs with identical filled_at, SPY/equity/buy/strike0/empty expiry cause the second INSERT to raise ConstraintException; row count stays1. The route catches this as journal_unavailable, so holdings are missing. Need collision-safe identity compatible with close-intent row attribution; do not fabricate a different execution timestamp or silently discard the second order.
3. **Cumulative fill regressing to zero misses reconciliation.** After the helper records one share of a requested two for a broker ID, a later same-ID filled_qty=0/price=None snapshot returns pending_fill, quantity=None, unfilled_qty=2. Existing journal still holds1. The early no-fill return bypasses existing-order comparison. A valid contradictory cumulative update should flag reconciliation_required, preserving the old holding rather than implying no fill. No false price or duplicate holding was created, but conflict visibility is missing.

## Confirmed working scope

The current merged-order tests completed **34 passed, zero skipped, 1 warning, 2.07s** under `--noconftest -p tests.offline_network`; evidence TEMP/floww-order-independent-2258.log. That suite covers partial/zero/full confirmed quantity and finite price, wrong attribution rejection, identical-ID duplicate suppression, increasing cumulative quantity requiring reconciliation, actual client transport of stop/stop-limit prices, wrong-order Discord readback rejection, disabled predispatch close leaving no reservation, and ambiguous dispatched close blocking retry.

These passes do not refute the three probes above, which are not represented by the suite at review time. Author was still adding final edges, so subsequent repairs need their own source/test evidence before closing findings. No live-enablement or future execution readiness is certified.

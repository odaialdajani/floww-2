# Liquid Paper capability policy

Version: liquid-paper-capability-gate-v1. Reviewed source, authenticated venue
reads and permission to submit are separate states.

The dedicated native Hermes profile is `floww-paper`. Its official MCP URL is
`https://coinvest-computer.liquid.trade/mcp`. OAuth credentials remain in the
native private store. The profile emergency pause and disabled connector stay
in place; research and coding workers receive no Liquid tools or credentials.

The November 7 authenticated catalog exposes `paper_trading_status`,
`get_account`, `get_portfolio`, `view_open_orders` and `execute_order`.
`execute_order` includes an idempotency key but its advertised input schema has
no execution-mode or simulated-destination binding. Tool descriptions refer to
execution mode elsewhere, but prose is not a supported parameter contract.

`ops/liquid_paper_adapter.py` validates only a current trusted read bundle:
fixed endpoint, matching case-insensitive account addresses, explicit trading
account role, exact boolean Paper flags on both portfolio and orders, successful
source statuses, finite balances and at most ten seconds of local read age.
It preserves existing simulated positions/orders and returns a fingerprint
instead of a raw account address. It has no credential or transport access.
Its successful attestation never grants order authority.

`submit_paper` refuses every call before any transport or ledger mutation.
Caller-supplied flags, model confidence, a Paper banner and an added schema
property cannot unlock it. Repeated status reads alone do not prevent a mode
change between checking and submitting. A reviewed server-enforced simulated
request/destination contract is required before implementing submission.

Observed November 7: dedicated OAuth succeeded. Paper was enabled through its
explicit native tool and automation remained disabled. The first portfolio read
after enable still returned `paper=false`; a later fresh portfolio and open-order
read both returned `paper=true` for the same wallet. The mismatch is retained in
the private execution receipt, not discarded as a successful commissioning.
An existing simulated position was observed and preserved. No order, close,
cancellation, balance reset, automation policy or real-fund action was submitted.

Liquid markets require their own verified instrument, sizing, fee, funding,
quote-time and exit policy. The internal equity-options $500-debit policy does
not define a Liquid perpetual policy. No option-to-perpetual mapping is allowed.
Commissioning also needs a separate durable intent ledger, timeout/restart
reconciliation and independent accounting review. Those execution capabilities
are not claimed by this read-only gate. Future market sessions and profitability
acceptance remain outstanding.

Evidence: `/Users/nav/floww-execution-20261107/liquid/` (private native catalog,
authentication result, contradictory and subsequent read receipts). Vendor
reference: [Co-Invest Computer](https://docs.liquid.trade/co-invest/co-invest-computer).

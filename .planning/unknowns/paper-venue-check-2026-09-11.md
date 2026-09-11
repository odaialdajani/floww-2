# Paper venue capability check

Decision: Retain the plan's internal default. No venue change, account connection or order was made. The internal implementation is still gated by the proposed accounting clarification and supported product lifecycle tests.

| Dimension | Internal simulation | Alpaca paper |
| --- | --- | --- |
| Existing local fit | Can isolate reproducible fixture tests; current local equity book is not sufficient for options | Requires a verified account binding and adapter beyond the current client |
| Options | Must implement and test each supported shape explicitly | Official documentation confirms options and multi-leg support, subject to account level and contract validation |
| Lifecycle | Must retain holdings and uncertainty when required data is missing | Exercise/assignment/expiry activities exist; paper activity visibility can lag until the next day |
| Fill realism | Must state simulated fill assumptions, spread, age, size and fees | A simulation with documented differences from live trading; not proof of executable results |
| Replay and recovery | Can make economic examples deterministic with bounded atomic account state | Requires external order/fill/activity reconciliation and idempotency tests |
| Current acceptance | Not accepted: accounting and lifecycle work remains | Not accepted: this account's entitlements and local integration have not been tested |

Primary sources checked 2026-09-11:
- [Alpaca options](https://docs.alpaca.markets/us/docs/options-trading)
- [Multi-leg options](https://docs.alpaca.markets/us/docs/options-level-3-trading)
- [Paper limitations](https://docs.alpaca.markets/us/docs/paper-trading)

These references establish provider capabilities, not this user's account authorization or production readiness.

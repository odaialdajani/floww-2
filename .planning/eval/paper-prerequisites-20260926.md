# Paper prerequisites and ownership - 2026-09-26

User explicitly requested all outstanding chart/scanner work and broader research/paper work. This thread owns paper preparation; integration/research thread 01a09111-6aed-79f1-9b95-2716073a7af8 owns research acceptance and shared application integration. No paper or live actions enabled.

## Initial constraints (historical; current correction below)

- Research acceptance remains open; proposals cannot be released before it passes. Paper additionally waits for validated proposals, accepted accounting, venue/lifecycle evidence, configured user risk limits and protected human confirmation.
- Internal simulation remains the accepted default. No account/provider switch is implied. Existing services/paper_broker.py is in-memory, uses generic share arithmetic, and does not implement the required durable options book.
- Accounting proposal docs/adr/0010-paper-accounting-proposed.md remains unaccepted. User was asked whether slippage should count once through worse fills on September26 at21:23UTC; answer pending. Offline examples are permitted by that proposal, but shipping or sharing the accounting change is blocked until acceptance. Historical backtest results and ADR0003 are preserved.
- New modules must have no broker/network imports and no live order capability. Paper action mounting requires the integration owner and passing release gates. Backend source remains stable until the currently running full backend check finishes.

## Refreshed venue comparison

| Required dimension | Internal simulation | Alpaca paper |
| --- | --- | --- |
| Shapes/products | Explicitly earn support through metadata, economics and lifecycle tests; no generic assumption that every option is100shares | Official documentation supports options and multi-leg orders; account level, symbol eligibility and local connection remain unverified |
| Executable fill basis | Fresh timestamped bid/ask plus displayed size, limits, configured fees/latency; labelled simulation assumptions | Eligible marketable fills use prevailing quotes, but documented paper rules do not restrict fills to displayed quantity and random partial fills occur |
| Reproducibility | Deterministic inputs, exact decimal accounting, immutable identities and saved events can be replayed | External evolving simulated fills require saved order/fill/activity reconciliation |
| Lifecycle | Must implement expiry/exercise/assignment/deliveries and retain uncertain holdings; unsupported products remain refused | Nontrade options activities include exercise/assignment/expiry; paper activity reporting can lag until next day |
| Costs and corporate events | Configured fees/slippage once plus explicit event data; missing lifecycle data freezes admission rather than fabricating completion | Official paper limitations exclude latency slippage, regulatory fees, dividends and other real-market effects |
| Current readiness | Not ready; accounting/research/proposal/lifecycle gates remain | Not verified for this account; not selected and no external paper order sent |

Primary sources refreshed this turn:
- https://docs.alpaca.markets/us/docs/paper-trading
- https://docs.alpaca.markets/us/docs/options-trading
- https://docs.alpaca.markets/us/docs/options-level-3-trading

## Bounded state design before implementation

One account document per owner/account/internal venue contains cash, signed position lots, open order reservations, durable risk/session state, sequence/version, idempotent operation identities and a bounded pending-event outbox. Proposed hard limits:128open structures,256openorders,1000retained operation identities and8MiBserialized account state. Refuse new exposure before these limits; keep existing positions readable and permit separately verified reduction. Never prune an uncertain fill or a pending projection to make space. Closed-account archival with stable identity tombstones is separate from risky silent pruning.

Every state transition and event seed commits together with an owner/account/venue/version condition. History projection upserts immutable event identity; a crash after account commit but before projection can be recovered without changing cash again. Retry with same identity/different economics refuses. Stores/down/casexhaustion fail explicitly; no in-memory fallback claims durability. Exact account recovery and concurrent last-buying-power tests must use a real isolated store.

Proposal and fill data must bind verified product identity, separate premium factor/deliverable, currency, exercise/settlement style, expiry instant, real source quote timestamps/sizes, fees, risk limits, evidence/claim IDs and a human-confirmed proposal version. No midpoint-fill assumption; no model-generated quantity or permission. Price-only slippage proposal remains pending user choice.


## Current correction - 2026-09-26 22:35 UTC

The earlier pending-accounting language is historical. User accepted all configurable slippage options at21:44: on/off and either worse price or explicit cash, never both. ADR0010 now records this acceptance. User allows choosing an existing owned paper account or setting up a new one; no account/capital/risk values were selected or invented. Backend freeze ended. Internal remains the venue default; no external paper account was selected.

Prepared unmounted modules now provide exact configurable arithmetic, bounded atomic storage/history, frozen-copy recovery, long single-leg fill transitions and a default-denied service. Their presence does not grant research/proposal/product/lifecycle acceptance. Working state now caps24retained orders and16prospective structures, with stricter actual space limits from reserved exit obligations; quote consumption max256rows. Entry reserves one bounded close attempt per structure,8new quote rows and12event credits. Close attempts require prior closes projected and archived; replenishment cannot erase retained close obligations or unexpired quote consumption. These replace the preliminary128/256/1000 aggregate limits above.

Final Python3.11 evidence:28unit checks;30real-Mongo storage checks (paper-storage-verification-20260926.json);17real-Mongo controller checks (paper-execution-verification-20260926.json). Frontend98suites/844tests and production build pass. Independent foundation, execution and settings reviews closed their reproduced findings. Synthetic isolated databases only. Includes restarted partial positions,12concurrent identical fill requests, hand-calculated1067.40endingcash/67.40result, journal tie, frozen quote mutation, and a close at the full valid pending-plus-reserved event limit. Not forced server crash or full option lifecycle proof.

Still absent: production account creation/listing/action mounting; verified proposal/contract metadata; account-session risk and marks; expiry/exercise/assignment/deliveries/corporate/dividend behavior; multi-leg/short support; actual full proposal-to-claim paper user flow. Research model comparison and external evidence gates remain separate. UI is device-local draft preparation only.

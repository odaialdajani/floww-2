# Public capability accounting

Reviewed November 1, 2026 against source `41c291cd333b02ec2ea6174a86bbfac11b5c6892`
plus the uncommitted account-route fix described below. This is a source and
mount inventory. It is not account entitlement, not provider acceptance and
not observed live behavior.

## The five populations

| Population | Count | Meaning |
| --- | --- | --- |
| Declared operation rows | 27 | `services/public_capability.py` registry |
| Rows naming a wrapper | 23 | rows 6, 7, 10 and 12 explicitly declare none |
| Unique wrapper methods | 22 | rows 15 and 16 share `PublicBroker.get_bars` |
| Public route paths actually mounted | 14 | of 394 paths in the running schema |
| Wrapper methods reachable from a mount or worker | 10 | plus 2 only inside an unmounted service, 10 with no caller |

These are separate denominators. A declared row does not imply a route, a
route does not imply an entitlement, and a wrapper does not imply observed
provider behavior.

## Declared rows to callers

`reachable` means a non-test caller exists on a mounted route or a running
background path. `unmounted` means the only call sits inside
`services/public_execution_lifecycle.py`, whose execution functions have no
non-test caller. `none` means no non-test caller.

| # | Operation | Wrapper | Caller / transport | Status |
| --- | --- | --- | --- | --- |
| 1 | create_token | `auth` | `_get_broker()` cold init behind every Public read | reachable |
| 2 | get_accounts | `get_accounts` | `_get_broker()` cold init | reachable |
| 3 | get_portfolio_v2 | `get_portfolio` | `/api/public/portfolio`, `/orders`, `/portfolio/raw` | reachable, authenticated |
| 4 | get_history | `get_history` | none | none |
| 5 | get_tax_lots | `get_unrealized_tax_lots` | none | none |
| 6 | get_tax_lots_symbol | declared none | none | no wrapper |
| 7 | get_tax_lots_csv | declared none | none | no wrapper |
| 8 | get_all_instruments | `get_all_instruments` | `services/market_catalog.py` stock directory | reachable |
| 9 | get_instrument | `get_instrument` | none | none |
| 10 | search_bonds | declared none | none | no wrapper |
| 11 | get_quotes | `get_quotes` | `/api/public/quotes`, chain spot, spot readers | reachable |
| 12 | get_bond_details | declared none | none | no wrapper |
| 13 | get_option_expirations | `get_option_expirations` | `/api/public/expirations`, chain assembly | reachable |
| 14 | get_option_chain | `get_option_chain` via `get_option_chain_parsed` | `/api/public/chain`, exposure route, flowseeker chain | reachable |
| 15 | get_bars_v2 | `get_bars` | `/api/public/bars`, history, technical | reachable |
| 16 | get_bars_agg | same `get_bars` | same callers | reachable |
| 17 | preflight_single | `preflight_single_leg` | lifecycle `preflight` only | unmounted |
| 18 | preflight_multi | `preflight_multi_leg` | none | none |
| 19 | place_order | `place_order` | `POST /api/public/order` | reachable, key + arming + admission |
| 20 | replace_order | `replace_order` | lifecycle `replace` only | unmounted, disarmed |
| 21 | search_orders | `search_orders` | none | none |
| 22 | get_order_v2 | `get_order_v2` | none | none |
| 23 | place_multileg | `place_multileg_order` | none | none, disarmed |
| 24 | get_order_legacy | `get_order` | lifecycle `reconcile` only | unmounted |
| 25 | cancel_order | `cancel_order` | `POST /api/public/order/{id}/cancel` | reachable, key required |
| 26 | get_greeks | `get_option_greeks` | none (chain rows carry vendor Greeks) | none |
| 27 | get_strategy_quote | `get_strategy_quote` | none | none |

## Mounted paths and transport

Market-data reads (`routes/public_api.py`, unauthenticated GETs by design):

- `/api/public/chain/{ticker}` and `.../exposure-by-strike` → adapter chain
  fetch with single-flight lock, stale-copy fallback, provider budget, then
  per-row exposure annotation.
- `/api/public/quotes/{ticker}` → adapter quote fetch.
- `/api/public/bars/{ticker}`, `/history/{ticker}`, `/technical/{ticker}/{indicator}`
  → adapter bars; technical is computed locally from those bars.
- `/api/public/expirations/{ticker}` → broker expiry read.
- `/api/public/portfolio/raw` → broker portfolio read; now requires the master
  key (see below).

Account and execution reads/writes (`routes/public_brokerage.py`):

- `/api/public/portfolio`, `/orders`, `/account`,
  `/execution-lifecycle/inventory` → authenticated GETs.
- `POST /api/public/order` → authenticated, validation, then
  `FLOWW_ENABLE_LIVE_PUBLIC == "1"`, then order admission and single-use
  approval consumption, then `place_order`.
- `POST /api/public/order/{id}/cancel` → authenticated; cancellation remains
  allowed while entry submission is disarmed.

Every broker call uses the in-repo `PublicBroker` HTTP client against
`api.public.com`. Chain and quote reads additionally pass the Public request
budget and adapter cache. No alternate provider substitutes for a refused
Public read.

## Reproduced boundary defect and fix

`GET /api/public/portfolio/raw` had no authentication dependency. Because the
application auth middleware protects mutating methods only, the route returned
the account id, cash and positions to an unauthenticated caller. This was
reproduced on the running service on November 1, 2026 during this inventory:
one GET returned `200` with account data. That call was the reproduction; it
was not repeated. No order, cancellation, mutation, account connection or
new provider spend occurred.

The route now declares `Depends(require_api_key)` and the regression file
covers missing key (401), wrong key (401) and unset server key (503). Seven
focused route checks pass; Ruff is clean. The managed backend was independently identified as d5cd2691 on November2,
which includes this authentication fix. No second unauthenticated account read
was made. This version check does not establish account-wide commissioning.

## Entitlement and observed evidence

- The registry classifies all 27 rows `entitlement: commissioning_required`
  and `observed: not_observed`. That is the default, not a denial for any
  account.
- Persisted `capability_observations_v1` rows in the current store cover
  `heatmap_build` for SPY and INFQ only. There are no stored per-operation
  broker observations (chain, quotes, bars, portfolio or orders), so the
  symbol matrix correctly reports `entitlement: unobserved` and
  `vex_inputs: unknown`.
- The in-memory measured manifest is `all_null_unknown_first`.
- No account or order was invoked to produce this ledger. Entitlement and
  live provider acceptance remain external holds. A successful data read
  would prove only that read, not account permission or trading readiness.

## What remains open

- Account entitlement evidence for any operation, per account, with a dated
  receipt.
- Observed provider behavior for the ten no-caller methods before any is
  presented as available.
- Commissioning decisions for capture, trading and any paid feed. None are
  authorized here.

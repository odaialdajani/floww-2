# SPARK R15-4 — Account/portfolio/journal/protection/expiry contracts (Spark → Zed)

Base `1530ccd7`. No new live path. All shapes are the existing
`routes/public_brokerage.py` read contracts + `public_execution_lifecycle.py`
(`execution-intent.v1`) validation rules. Protected friend workspaces keep
their domain meaning; Public data never overwrites proprietary flow.

## Read contracts (existing, authenticated, 502 when key/account/API missing)

- `GET /api/public/account` → `{ok, account_id, account_number?, status,
  total_account_value?, buying_power?, cash?, initial_margin, maintenance_margin,
  day_trading_buying_power?, portfolio_value?, data_source:"public_api"}`.
  Unknown money stays null (reads) — except legacy `_parse_money` zero-fills on
  the `/account` route only (documented quirk; `/portfolio` preserves null).
  Zed: prefer `/portfolio` nulls for display; do not render zero as a holding.
- `GET /api/public/portfolio` → `{ok, account_id, buying_power?, 
  options_buying_power?, cash?, initial_margin?, maintenance_margin?,
  portfolio_value?, positions:[{symbol,name,quantity?,current_price?,
  market_value?,cost_basis?,day_gain_pct?,total_gain_pct?,pnl?,asset_type,
  bid?,ask?}], position_count, data_source}`. Sorted by |market_value|.
  Unknown stays unknown; measured-zero stays zero.
- `GET /api/public/orders` → `{ok, orders:[{order_id,symbol,side,type,status,
  quantity,filled_quantity,price?,limit_price?,time_in_force,created_at?,
  updated_at?,filled_at?}], order_count}`. Non-terminal = open (client-side
  filter via `get_open_orders`); terminal FILLED/CANCELED/REJECTED.
- Freshness: portfolio/orders carry no vendor event clock beyond the fetch;
  quotes carry `timestamp/bid_timestamp/ask_timestamp` + `spot_source/
  spot_event_time/spot_fetched_at`. Stale keeps actual ages; crossed/wide/stale
  books degrade with reason (`crossed-book|wide-book|stale-quote`), never a
  fabricated mid.

## Journal / protection / expiry (lifecycle-enforced, `execution-intent.v1`)

- Journal: intent → approval → submission → acknowledge/open/partial/filled/
  rejected/cancel/replace/unknown. `*_INTENTS` registry persists ownership +
  broker `orderId` + original payload; retries reuse both; a changed order
  requires a NEW intent (in-place `replace` is refused).
- Protection: only broker-native protection where the exact product/order
  combination is supported AND the account is eligible is offered. Incomplete
  protection is never called `protected` (`protection_status→{protected:false}`
  until verified). Stop ≠ guaranteed ceiling. Partial entries track
  `filled_quantity` truthfully; acknowledged ≠ filled.
- Expiry/roll: `supported_expiries` allowlist enforced; near-expiry entry cutoff,
  liquidity checks, assignment/exercise exposure, and unsupported-case refusal
  are commissioning policy (operator + Zed final review). Past-expiry dates are
  refused by the allowlist in this lane; calendar-day cutoff is a follow-up.
- Expiry-coverage truth (verified 3 Oct 2026 against `public_api_adapter.py`):
  chain coverage is COUNT-based, not DTE-windowed — `max_expiries` accepted
  expiries (default 4, callers up to 6), expired contracts dropped, 0DTE kept
  with exact T. No backend DTE30 cap and no admitted 14–60DTE window exist
  anywhere in the chain path (searched); requested-vs-returned coverage is
  distinguished per fetch. An admitted DTE range remains COMMISSIONING policy
  (account-specific, set alongside `supported_expiries`), not code — inventing
  a window here would silently narrow data Zed's workspaces rely on.
- Entry pause 11:30–14:00 America/New_York blocks new backend entries
  (`ENTRY_PAUSE`); cancels, risk exits, and reconciliation stay available
  independent of LLM availability.
- Cash/margin is explicit (`CASH|MARGIN`, no vendor-default inheritance).
  Preflight (`preflight_single_leg/multi`) is fresh per intent hash and expires
  on any change; estimates/rebates/buying-power checks are NOT fill economics.
- Native overlap: `PUBLIC_NATIVE_AGENT` vs `FLOWW_BACKEND` ownership persisted;
  an OPEN native workflow created outside FLOWW blocks backend entry
  (`OVERLAP_NATIVE`); open/unknown broker orders block new entry until
  reconciled by `orderId` (`OVERLAP_OPEN_NEEDS_RECONCILE`).

## Refusals (exact codes for Zed UI)

`BAD_CONTRACT|UNSUPPORTED_PRODUCT|UNSUPPORTED_EXPIRY|STALE_QUOTE|
MISSING_QUOTE_SIDES|MISSING_POLICY|UNRESOLVED_MARGIN|UNAUTHORIZED_REPLAY|
ENTITLEMENT_UNAVAILABLE|BAD_TICK|RISK_QUANTITY_EXCEEDED|RISK_NOTIONAL_EXCEEDED|
RISK_MAX_POSITIONS_EXCEEDED|OVERLAP_NATIVE|SESSION_CLOSED|ENTRY_PAUSE|DISARMED|
STALE_PREFLIGHT|APPROVAL_INVALID|STORE_UNAVAILABLE|AMBIGUOUS_NEEDS_RECONCILE|
OVERLAP_OPEN_NEEDS_RECONCILE|SUPERSEDE_BLOCKED` (+ HTTP
`401/403 live_trading_disabled/422/502 no_public_api_key|no_account|api_error`).

Research-only `/api/agent/*` auth never authorizes execution/account mutation.

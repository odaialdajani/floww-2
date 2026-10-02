# SPARK R15-1 — Public capability + auth truth matrix (Spark → Zed)

Base: `1530ccd7`. Contract: `public-capability.v1` (27 ops, docs reviewed
2026-09-23, SDK `PublicDotCom/publicdotcom-py@00dca7d`).

## Code truth (replaces stale prose)

- `routes/public_brokerage.py` IS mounted (`server.py:3668-3670`,
  `prefix="/api"` + router `prefix="/public"`). Live paths:
  `GET /api/public/portfolio|orders|account` (reads, 502 when key/account/API
  unreachable, unknown stays unknown, never zero-filled),
  `POST /api/public/order` (validates 422 first, then 403 `live_trading_disabled`
  unless `FLOWW_ENABLE_LIVE_PUBLIC` exactly `"1"`; broker never touched while
  disarmed), `POST /api/public/order/{id}/cancel` (authenticated, available
  while disarmed).
- Every brokerage endpoint requires master key (`Depends(require_api_key)`,
  401 without/mismatch). Global `verify_api_key` is fail-closed 503 when
  unconfigured; `research_path` bypass is `/api/agent/*` only.
- `services/public_capability.py:37` prose
  (`"PublicBroker.place_order (UNGATED LIVE — disarmed, no route)"`) is STALE:
  the route exists and is gated. Queued fix (one-line prose + `writes:true`
  already correct) — NOT applied in this increment to keep the diff
  services-only. Zed: treat the code + this note as truth, not the old string.
- `services/public_api_adapter.py` stays data-only (pinned by
  `test_adapter_has_no_order_method`). No MCP execution tools to browser/Lodestar.
- Alpaca PAPER is a separate venue/account (`routes/alpaca.py` → paper host,
  safe by construction). Quick Trade PAPER does NOT imply Public migration.
  Research-only `/api/agent/*` auth never authorizes broker execution.

## Per-capability matrix (summary; full JSON: `r15/evidence/public_matrix_v1.json`)

| # | op | documented | installed | entitlement | tested | consumer | refusal |
|---|----|------------|-----------|-------------|--------|----------|---------|
| 1-5 | token/accounts/portfolio/history/tax-lots | vendor docs | `PublicBroker.*` present | commissioning_required | mocked_only | Portfolio/Journal/Broker | `no_public_api_key`→502; `no_account`→502 |
| 6-7,10,12 | tax-lots-symbol/csv, bonds search/details | vendor docs | NONE (wrapper null) | commissioning_required | none | — | `unsupported-capability` (labeled unknown) |
| 8-9 | instruments | vendor docs | present | commissioning_required | mocked_only | Triad/Portfolio | 502 when unreachable |
| 11,13-16,26 | quotes/expirations/chain/bars/greeks | vendor docs | present via adapter (chain/quotes/bars wired; greeks preserved with source clocks) | commissioning_required | mocked_only + chain/quote regression | Solstice/Triad/Heatseeker | stale/crossed/wide-book → degraded + reason; OI unknown stays null; GREEK_TIME_UNKNOWN on vendor path |
| 17-18,27 | preflight single/multi, strategy quote | vendor docs | present | commissioning_required | mocked_only | Broker preflight | `validateOrder` honored; estimates are NOT fills |
| 19,23 | place single/multi-leg | vendor docs | present, LIVE gateway | commissioning_required + `FLOWW_ENABLE_LIVE_PUBLIC==1` + API key | mocked_only + gate tests (403 before broker) | Broker (gated) | `live_trading_disabled`→403 disarmed; 422 validation holds while disarmed |
| 20,25 | replace/cancel | vendor docs | present (DELETE-fixed cancel; replace closing-leg-only) | commissioning_required (+ gate for replace path) | mocked_only | Broker | cancel available disarmed; pending≠canceled |
| 21-22,24 | search/get_order_v2/legacy | vendor docs | present | commissioning_required | mocked_only | Broker reconcile | UNKNOWN stays unknown |

Entitlement is per product/account and CANNOT be inferred from a key being
present. Documented ≠ installed ≠ entitled ≠ observed. Chain volume/OI is not
an executed trade-print feed, aggressor signal, or dealer inventory.
Server-observed freshness (`event_time` vs `fetched_at`, OI date, quote ages)
is exposed; stale quotes keep actual ages.

## Evidence

- Code-read at `1530ccd7` (`public_brokerage.py:46-60`, `server.py:3664-3670`,
  `auth.py:69-101`, `public_api_adapter.py:23-25`).
- Offline tests (no live calls): `test_public_brokerage_gate` (403 before broker
  for 6 disarmed settings), `test_public_brokerage_auth` (401/403/422/200 matrix),
  `test_adapter_has_no_order_method`, `test_solstice_exec_disarmed`.
- Fixture: `docs/solstice/r15/evidence/public_matrix_v1.json` (27 ops enriched).

# SPARK R15 — Operator commissioning policy + rollback (Spark → Nav/Zed review)

Status: **policy only — NOT authorized, NOT activated.** This document specifies
the exact steps an operator (Nav) must approve and record before the R15
services do anything beyond their current default-off behavior. It complements
Zed's `COMMISSIONING_PACKAGE.md` (R5-F durable capture, read-only here) and
covers only what R15 added: the scheduled price-path producer and the
deterministic execution lifecycle. No step below has been performed.

## 0. What is already live vs what needs commissioning

| Item | State today | Needs |
|---|---|---|
| Price-path producer code + fetch seam + status routes | Merged only after PR94 review; currently OFF | Code review (PR94), then §1 |
| Producer scheduling/activation | `FLOWW_PRICE_PATH_PRODUCER` unset → `start_worker` refuses; status reports `wired_off`/`absent` | Explicit §1 authorization |
| Durable store | `DUCKDB_PATH` unset → `:memory:`, `durable:false` | Zed's package §1 + §5 restart proof |
| Execution lifecycle | Pure service, no route, `armed=False` default; no broker calls | §2 approval-desk setup; venue arming stays a separate Nav decision |
| Live orders | None by any path in this lane | NEVER under this policy without §2 + venue gate |

## 1. Price-path producer activation policy

Prerequisites (ALL required, recorded in the approval request):
1. PR94 reviewed + merged; exact-head gates green (receipt §Verification).
2. `DUCKDB_PATH` points at the commissioned file store (see Zed's package §1);
   `GET /api/solstice/recorder_health` reports `durable:true` on a throwaway
   restart proof first (their §5).
3. `FLOWW_PRICE_PATH_SYMBOLS` allowlist reviewed (default `SPY,QQQ`; hard cap 32
   enforced in code). Triad intraday needs ≤5-min cadence (default 300s); swing
   research may use slower cadences. Cadence is code-level (`cadence_s=300`);
   changing it is a config PR, not an env edit.
4. One week of disk-growth measurement before retention tiers (their §2 math:
   ~78 snapshots/symbol/session for structural builds; price-path rows are
   smaller — ~1 row/symbol/tick, ≈78 rows/symbol/session at 300s).

Activation (exact, reversible):
1. Set `FLOWW_PRICE_PATH_PRODUCER=1` on the backend process ONLY (never in a
   committed file). Restart the process.
2. Verify: `GET /api/solstice/price-paths/status` → `worker_enabled:true`,
   `worker_state:active`, `generation` set; `captures` increments each cadence;
   `gaps`/`closed_skips`/`budget_refusals` explain every non-write (no silent
   zeros; closed sessions skip without provider calls).
3. Soak one full session; check `GET /api/solstice/price-paths/points?ticker=SPY`
   continuity + `manifest` gaps. Any unexplained gap rate → §3 rollback.

Rollback (exact):
1. Unset `FLOWW_PRICE_PATH_PRODUCER` (or stop the service) → next
   `start_worker` refuses; in-flight thread stops via `stop_worker()` on
   shutdown. Analytics continue; status returns to `wired_off`.
2. Stored `price_paths_v1` rows are append-only history — leave them (labeling
   treats absence as gaps, never interpolates). To discard a bad window, record
   the reason; do not delete rows silently.
3. Code rollback: revert the R15 merge SHA; migrations are additive
   (`ADD COLUMN IF NOT EXISTS` / `CREATE TABLE IF NOT EXISTS`), so old readers
   ignore new tables/columns.

## 2. Execution lifecycle commissioning policy

1. The lifecycle stays a library until a production caller exists. Any future
   HTTP caller MUST: require API key (existing `require_api_key`), pass
   `armed` ONLY after checking `FLOWW_ENABLE_LIVE_PUBLIC==1` itself (the service
   never reads the flag), and pass `require_approval=True` with a
   server-issued approval (see `create_approval`/`verify_approval`). Client
   booleans and model text are never authorization.
2. Approval desk (operator-owned): approvals bind intent_hash + account + scope +
   validity window (default 30 min). Expired scope refuses (`APPROVAL_INVALID`);
   never silently re-arm. On restart: run `reconcile_all` before any new entry;
   open/unknown orders block entry (`OVERLAP_OPEN_NEEDS_RECONCILE`) until
   reconciled by broker `orderId`.
3. Venue arming (`FLOWW_ENABLE_LIVE_PUBLIC=1`), account funding/margin policy,
   and risk limits are Nav decisions OUTSIDE this policy — this document grants
   no live-order authority. A separate real-money commissioning record with
   fixed account policy, size caps, and kill-switch drill is required first, and
   Zed must review it as final integration owner.
4. No automatic escalation, ever: no Kelly sizing, no retraining, no parameter
   changes on outcomes. 30–60 sessions is a collection milestone, not a pass.

## 3. Kill-switch drill (before any live consideration)

1. Disarm: unset the venue flag → `POST /api/public/order` returns 403
   `live_trading_disabled` without touching the broker (pinned by gate tests).
2. Cancel: authenticated `POST /api/public/order/{id}/cancel` still works while
   disarmed (intentional).
3. Producer: unset its flag → status returns to `wired_off`; rows already stored
   remain queryable history.

## 4. What commissioning NEVER grants

Live trading authority, credential changes, vendor messages, multi-user data
redistribution (Public Individual API is personal-use), predictive-performance
claims, or SPX/entitlement/data-rights resolution. See also Zed's package §6.

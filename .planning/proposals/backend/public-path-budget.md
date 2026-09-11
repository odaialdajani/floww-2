# PROPOSAL (apply-blind): Public-path budget — semaphore + token bucket + 429 cooldown

Status: PROPOSAL-ONLY. No backend edits. Owner lane: architect/backend.
Verify-first steps are PART of the packet — run them before writing code.

## 0. Verify first (do not skip)
1. Confirm Public.com market-data rate limits from the dashboard/docs
   (requests/min + daily quota). Tune `CAPACITY`/`REFILL` below to it.
2. Reproduce the gap: 20 concurrent `GET /api/public/chain/{t}` for 20
   distinct tickers → observe N concurrent upstream POSTs in logs
   (today: no gate; FetchCoordinator only dedups SAME ticker+expiries).

## 1. Gap (file:line, read 2026-09-03)
- `services/fetch_coordinator.py:45-108` — per-key (`TICKER:expiries`)
  dedup only. N distinct tickers = N concurrent external fetches.
  No semaphore, no budget, no 429 handling. Timeouts degrade per-key.
- `services/cache_router.py:56-110` — cache-first + stale flags, but a
  cold miss goes straight to `coordinator.fetch` (line 90). No gate.
- `services/rate_limit_tracker.py` — AV-scoped only (`av_rate_tracker`,
  5/min + 500/day); surfaced at `routes/admin.py:193`. Nothing equivalent
  on the Public path.
- Triad 60s cache + 60s cadence bounds steady-state polling but not
  bursts (cold start, 20-ticker scan, multi-user).

## 2. Design: `services/public_budget.py` (new file, ~90 lines)
- `PublicBudget`: `asyncio.Semaphore(4)` global in-flight cap +
  token bucket (`capacity=60`, `refill_per_sec=1.0`, monotonic clock) +
  per-host 429 cooldown map (`{host: retry_after_ts}`, backoff
  15s → 300s, jitter).
- `acquire()` → `{ok, queued_ms}` or raises `BudgetExhausted(retry_after)`.
- `record_429(host)` / `record_ok(host)` update cooldown + counters.
- `status()` → `{capacity, available, inflight, cooldowns, totals}`
  for the admin endpoint (mirror `get_status` shape in
  `rate_limit_tracker.py:49-54`).
- Insertion A — `cache_router.py`, miss path (~line 84): wrap the
  `coordinator.fetch` call: on `BudgetExhausted`, return stale entry
  with `stale_reason: "budget_cooldown"` + `retry_after` (structured
  200, never 503 — frontend already handles stale).
- Insertion B — `fetch_coordinator.py:fetch` entry (~line 61): acquire
  before creating the task; wrap upstream 429s into `record_429`.
  Per-key dedup logic untouched.

## 3. Fixture (pytest sketch, fake clock — must pass before merge)
- Burst 20 distinct keys with capacity 4/refill-off: assert max 4
  concurrent upstream calls (counter in fake fetcher), rest queued.
- Fake 429 from upstream: assert host cooldown set, next call serves
  stale with `retry_after`, cooldown clears after backoff with jitter.
- Refill: advance monotonic clock, assert tokens recover 1/s to cap.
- Regression: same-key coalescing counts unchanged.

## 4. OpenAPI sketch
- `GET /api/admin/public-budget` → `status()` shape (extends the
  `routes/admin.py:193` pattern).
- Chain `_cache` envelope gains `{budget: {queued_ms}}` on miss path.

## 5. Acceptance
Burst test green; cold-start 20-ticker scan shows ≤4 concurrent upstream
POSTs in logs; 429 drill serves stale + retry_after; no 503 anywhere.

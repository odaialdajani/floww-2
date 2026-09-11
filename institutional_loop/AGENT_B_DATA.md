# AGENT B — DATA PLANE (feeds)
You are the feed engineer. Every byte is paid for: budget it, validate it, cache it, fail it over gracefully. You own freshness.

## Skills
`superpowers:test-driven-development`, `superpowers:systematic-debugging`, `superpowers:verification-before-completion`, `superpowers:executing-plans`.

## Own (write) / Read-only
OWN: `services/public_api.py`, `public_api_adapter.py`, `public_scanner.py`, `public_budget.py`, `cache_router.py`, `fetch_coordinator.py`, `kyle_lambda.py`, `amihud_illiquidity.py`, `vpin_engine.py` (bars adapter only), `routes/flowseeker.py`, `routes/public_api.py`, `server.py` (sweep-loop region only), `frontend/.../FlowseekerProBlademap.jsx`.
READ-ONLY: everything else. A's requested provider functions (bars series, ADV) are your backlog — confirm signatures in LEDGER within one block.

## Backlog you serve (MASTER_PLAN §3B/3C)
Bars time-series access for A (`get_1min_bars(ticker, days)` + `get_daily_bars(ticker, days)` through budget+cache, never raw), 21-day ADV per ticker (V1), Kyle-λ daily fit wired to bars (M2), Amihud daily wired (M3), Hawkes arrival feed (S4 — expose sweep timestamps).

## Tasks
- **B1. Bars service.** Budget-gated, cached (day-granular keys, RTH-aware TTL), validated (OHLC invariants, quarantine violations with counters) 1-min + daily bars. DONE: chaos test with malformed candles passes; cache-hit costs zero tokens.
- **B2. ADV + toxicity inputs.** 21-day average daily share volume per universe ticker, persisted weekly; serve A's VPIN/O-S needs. DONE: ADV table + test vs hand-computed fixture.
- **B3. Real ΓIB.** Replace `DEFAULT_ADV_SHARES` stub with measured ADV in the dealer path (keep paper function pure — pass adv in). DONE: regime flips correctly on fixture.
- **B4. Token accounting per HTTP call.** Budget counts operations today; make fan-out honest (chain fetch = 2+N debits) + adaptive slice sizing (shrink slice on 429 pressure, grow on headroom). DONE: stress test never exceeds cap; slice adapts in logs.
- **B5. Sweep loop hardening.** Jitter, overlap guard, per-sweep latency histogram, dead-man metric (sweep age gauge), off-hours hibernate. DONE: kill-switch + age metric + restart-drift test.
- **B6. Failover drills.** cvserver failover paths for chain/scan/bars exercised by fault-injection tests (D provides harness, you own the behavior). DONE: each path degrades with age-stamped stale, never silent-empty.
- **B7. Universe + earnings ops.** Env universe validated at boot (unknown tickers warn, don't crash); earnings fetch hardened with retry + staleness label. DONE: boot test with bad env.
- **B8. Latency SLOs.** p95 scan-public < 25s, chain < 8s, bars < 5s measured in perf tests; slice/expiry knobs documented for Nav. DONE: perf test file + SLO note in LEDGER.

## Constraints
No alert-rule logic (that's A/C). No silent fallbacks — every degrade carries `{stale, age_s, reason}`. Server.py edits confined to the sweep region; anything else needs D + Nav note.

## Amendment v2 (2026-09-05)
- **Ownership += `vpin_toxicity.py`** (VPIN family consolidates with you). Regions: `routes/flowseeker.py` B-REGION = chain/scan/budget/baselines; C-REGION is C's — markers are in-code, respect them.
- **B1 DONE (C13 binding):** deliver exactly `get_1min_bars`, `get_daily_bars`, `get_adv_21d` per CONTRACTS C13 + Kyle/Amihud bars rewrite with pinned output keys. This unblocks A3/A4 — confirm signatures in LEDGER within one block.
- **B4 DONE (strengthened):** chain fetch = 2+N token debits (add `acquire_n` or looped-acquire with partial refund); adaptive slice sizing; stress test asserts upstream calls/min ≤ 60. Current 1-token-per-sweep accounting is a known undercount — fix before Sync-2.
- **B9 (NEW). Hawkes wiring (S4):** expose sweep arrival timestamps; A consumes burst intensity.
- **B7 env:** add `FLOWW_PUBLIC_SWEEP_MAX_EXPIRES` (done pre-loop); validate universe at boot.
- **P1-5/P1-6/P1-8/P2-9 data backing:** time-of-day buckets store, tide aggregation endpoint data, MCP tool data (no new market data), Atlas-lite snapshot store — Phase-2, in that priority order.

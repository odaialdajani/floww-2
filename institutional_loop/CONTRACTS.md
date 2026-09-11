# SHARED CONTRACTS — frozen shapes for the 4-agent loop
Change only by unanimous agreement, logged in LEDGER.md with reason + migration. Version: v1 (2026-09-05).

## C1. Scan list-rows (10 cols, positional — NEVER reorder, append only)
`[underlying_ticker, ticker(OCC/osi), contract_type("call"/"put"), strike_price, expiration_date(YYYY-MM-DD), day_volume, open_interest, implied_volatility(decimal-or-percent, <3 = decimal), delta, underlying_price]`
Readers use the `SCAN_COLUMNS` name map, never bare indexes in new code.

## C2. ckey (contract identity, both languages)
Python: `f"{under}|{typ}|{strike:g}|{exp}"` · JS: `` `${r.under}|${r.type}|${r.strike}|${r.exp}` ``
`type` ∈ {call, put} lowercase. Decimal strikes must round-trip (`142.5` both sides). Verified by `test_ckey_matches_norm_rows_and_frontend`.

## C3. quote_truth extras (paid path only), keyed by ckey
`{premium_true: float|None (mid×vol×100), side: BUY|SELL|FLOW, nbbo_side: ASK|BID|None, signed_side: ASK|BID|None (Lee-Ready, quote rule + tick on prev sweep mid), sign_method: quote|tick|None, bias: BULLISH|BEARISH|None, mid, last, rel_spread: float|None ((ask-bid)/mid), vol_delta|None, velocity_per_min|None}`
Rules: None = unknown (never 0-as-dead); premium_true replaces BS estimates only when > 0; no extras key ⇒ row scores exactly as before. Engine preference: signed_side > nbbo_side > vol/OI proxy.

## C4. dealer context per ticker
`{call_wall: strike|None, put_wall: strike|None, max_oi_strike|None, net_gex: float|None (dealer-signed dollars), regime: "negative"|"positive"|None, gamma_imbalance_pct: float|None (measured vs 21d ADV, else None), adv_shares: float|None, roll_spread: {spread|None, n, nd, building, truncated}|None (pooled Roll over ticker rings; building until ~30 deltas)}`
No ADV guesses: pct/adv are None without measured ADV. Regime vocabulary is ONLY negative/positive/None everywhere downstream.

## C5. gex_context for the alert engine
`{underlying: {"gamma_imbalance": {"gamma_imbalance_pct": float, "regime": str, ...}}}` (ticker-keyed).
`_common_factors` also tolerates flat `{"gamma_imbalance": ...}` (unit-test shape). Regime normalized at the boundary via `_norm_gex_regime`.
Dealer fallback (no heatmap ΓIB): `{"gamma_imbalance": {"gamma_imbalance_pct": null, "regime": "negative"|"positive"|None, "dealer_walls": {...}}}` — pct **null** (unknown), never 0.0. Null propagates regime only and forces `gex_confluent=False`.

## C6. Alert dict (engine output — additive only)
Keys: `key(rule|ckey, namespaced), ckey, rule ∈ {OICONF,SCORE,WHALE,PRIME,0DTE,SIGMA,CLUSTER}, tier, conviction, side ∈ {BUY,SELL,FLOW,STRATEGY}, bias|None, under, type, strike, exp, dte, score, est_entry, premium(+premium_truth flag), notional, vol_oi, sigma, oi_chg_pct, under_price, key_levels{entry,invalidation,target}|None, context{activity_summary,institutional_indicators,market_regime,dealer_positioning}, cluster bool, cw_spread, why, ttl_s, asof, mins_since_open, p_move|None, p_method`.
Precedence: OICONF > SCORE > WHALE > PRIME > 0DTE (one per contract); SIGMA/CLUSTER ticker-level. TTLs: OICONF 20h, SIGMA 4h, SCORE 2h, PRIME 2h, CLUSTER 4h, WHALE 6h, 0DTE 1h.
0DTE gate (both languages): score≥85 AND vol_oi≥2 AND dte≤1. `perTickerCap=2` is frontend-notification-only; the backend feed never caps (completeness) — documented divergence.
Always-emit keys: `premium_truth: bool`, `p_move` (None until staged), `p_method` ("uncalibrated" until staged), `mins_since_open`, `rel_spread` (None without two-sided quote; C4 execution input).

## C7. Scoring locks
`scan_score` ≡ `scanScoreOf` term-for-term (pos .34 / size .24 / notl .18 / urg .14 / otm .10, regime nudge +5/3, informed band +4). Gating uses score; ranking uses conviction (`score_conviction` + evidence bonuses, backend-only). GEX S¹ (features) vs S² (display) duality untouched.

## C8. Budgets & caches
Public budget units = upstream HTTP calls; 60/min assumption, token bucket + inflight cap + 429 cooler. Chain fan-out debited per ticker (`acquire_n(2+N)`; skipped tickers keep prior slices, slices trim to affordability, unaffordable sweep raises). Route/sweep admission holds 1 op-token on top. cvserver: 20/hr total, scan slice ≈14, TTL 240s. Chain caches: adapter 60s + coalescing + stale-serve; flowseeker chain 600s LRU-500. Every stale payload carries age; empty-with-stale beats silent-empty.

## C9. Time & session
America/New_York for all session math. RTH sweep 45s / off-hours 600s. DTE = business days. Weekend/holiday rows are stale duplicates — history hygiene (`cleanHistory`) stays.

## C10. Money-loop fields
Paper trades carry `alert_key, entry_idea{entry,invalidation,target}, size_basis(Kelly-capped fraction + λ/slippage note), p_move, p_method`. Outcomes: multi-horizon returns vs SPY benchmark + t-stats; calibration stages gated by min-n (stage≥1 needs n≥60 per bin).

## C11. Logging & health
`structlog`-style fields where present; background loops log start/skip/error/shutdown; every skip states why (budget/cooldown/off-hours). Health must expose: feed status × budget tokens × sweep age × alert counts × calibration stage.

## C12. Forbidden files (need Nav — this list governs, subsumes the plan's short list)
`backend/services/ml/inference.py`, `backend/services/dash_ui.py`, `backend/tests/conftest.py` (waiver rules apply), model artifacts (`*.joblib/*.pt/*manifest*/*meta*` under `backend/models/`), `frontend/.env`, `frontend/package.json`, `frontend/craco.config.js`, `frontend/src/App.js` (surgical only).

## C13. Bars/ADV provider contract (Agent B provides, Agent A consumes)
- `get_1min_bars(ticker, days) -> [{t,o,h,l,c,v}]`, `get_daily_bars(ticker, days) -> [...]`, `get_adv_21d(ticker) -> float|None`.
- All budget-gated + cached (day-granular keys, RTH-aware TTL) + validated (OHLC invariants; violations quarantined with counters).
- Failures return `{stale, age_s, reason}` shapes downstream, never raise into callers.
- A consumes bars-lists only (no network in A modules). Kyle/Amihud bars-methodology rewrite is B-owned; output keys `{lambda_value, amihud, ...}` pinned by one test each.

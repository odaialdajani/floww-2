# Wave-2 paper synthesis (task 41) — what ships, what waits, what's banned

Sources: `/tmp/wf_wave2_cost.md` (40 claims), `/tmp/wf_wave2_0dte.md` (34 claims +
17 idea cards), `/tmp/wf_wave2_flow.md` (3 ideas, ticket-mapped). No repo touched
by researchers; all verdicts re-checked against Phase 9 PLAN constraints below.

## Corrections to researcher ticket maps
- There is no B4 (folded into B6/B7, PLAN line 77). All "B4 fixture" refs → B6.
- Amihud DOWNGRADED to FIXTURE-FIRST: researchers assumed daily history; the
  50-snapshot intraday cap holds no 5/20-day series. Shippable only after W4 store.
- Roll needs 30-60 snapshots but the trailing buffer holds 6 (90s). Shippable
  form requires a mid-history extension (per-contract mid ring, ~60 points,
  localStorage-persisted) — frontend-only, but it is a real build item, not free.
- Earnings SHIPPABLEs depend on a Finnhub-calendar spike: frontend-direct fetch
  needs a CORS/rate go/no-go (W0-style, one cheap test), else they fall to B2.

## SHIP list (frontend lane, no backend, Jest-provable)
1. Pin-risk panel: dist-to-max-OI + top-3 OI concentration % + 0DTE-OI share;
   Friday-only gate for single names, daily for SPX/SPY/QQQ/IWM. (W2 col + W3 modal)
2. Unsigned ATM-gamma-per-$ gauge, labeled "magnitude, direction unknown". (W3)
3. Skew raw levels in modal: XZZ smirk, C-W spread, Yan slope, convexity —
   delta-interpolated, front liquid monthly, spread-filtered mids. Needs
   `interpDeltaIV` helper + tests. (W3)
4. Inventory proxies per poll: midpoint-drift arrow, quote-skew tag,
   relative-spread column, cross-strike stress panel. All quote-only. (W3/W4)
5. Crowded/attention amber badge (update freq + spread + OI); copy gate: never
   directional, never "retail". (W3, B6 copy rule already covers)
6. Heuristic burst tag as EMA-of-delta extension of highlightState (never
   calibrated eta, never "Hawkes" branding in UI). (W3)
7. Roll pooled spread (per-expiry/moneyness, floored 0, n-obs shown) — AFTER the
   mid-history extension ships. (W2)
8. Earnings countdown + implied-move % + pre/post crush card — AFTER calendar
   spike passes, else B2. (W2/W3)

## FIXTURE-FIRST (no UI number until harness passes)
Hasbrouck-lite lambda-proxy; ex-earnings IV; skew percentile/quintile;
pin-hit-rate; last-N-earnings history; calibrated Hawkes eta (≥200 events,
eta<1 gate); Amihud rank; Roll/EDGE without day bars.

## BANNED (do not ticket — fabrication on snapshot data)
Signed GEX regime badge; 0DTE volume-share-as-signal; intraday flip feed;
PEAD score/timing; VPIN display anywhere on scan path (stays B1-quarantined,
unblocks only on tape entitlement B7); any "retail bought/sold" copy;
6-month persistence marketing copy.

## Researcher claims explicitly adopted as desk rules
- Cboe balanced-flow (CL-02/03): kills volume-as-signal AND signed badges.
- Single-name 0DTE exists only Friday (CL-06): gate the UI, not just docs.
- Smirk is cross-sectional (CL-31): no single-ticker "steep" badge without universe.
- Binned Hawkes needs 100+ bins (flow-idea-1): 6-bin buffer is heuristic-only.
- BJZZ post-2016 decay + 28% mis-sign (flow-idea-3): attention-context only.

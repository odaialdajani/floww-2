# Modal-hook contract (fixture-first, Step 1.1/1.3 polish — no surface edits)

Owner of the surface: Agent 2 (chart/ChartModal). This file + fixtures are
the complete integration input — no Blademap edits needed on either side.

## Hooks (pure, already shipped + tested in scanLogic.js)
- `skewLevels(rows)` — rows for ONE expiry with `iv` + `delta` →
  `{smirk, cwSpread, yanSlope, convexity}` (nulls where uncomputable;
  never extrapolates). Definitions: XZZ smirk = IVput(−0.2)−IVcall(0.5);
  C-W = IVcall(0.5)−IVput(−0.5); Yan = IVput(−0.2)−IVput(−0.5);
  convexity = IVput(−0.2)+IVput(−0.8)−2·IVcall(0.5).
- `quoteSkew(bid, ask, prevMid=null)` → `{mid, relSpread, driftBp, tag}`.
  Direction ONLY vs prevMid; without it tag is `LEVEL`, never a side.
- `pinRisk(rows, spot)` → `{maxOiStrike, maxOi, concentration, totalOi,
  distPct}`. `nearestExpiryPin(rows, ticker, now)` adds the Friday gate.

## Fixtures (frozen live snapshot 2026-09-03, SPY spot 773.21)
- `skew_levels_spy_20260903.json` — per-expiry `{n, skew, pin}` for the
  front 3 expiries. Front (2026-09-04): pin 765, smirk +0.67pp.
- `inventory_proxies_spy_20260903.json` — top-10 contracts by volume
  with `{mid, relSpread, driftBp: null, tag: "LEVEL"}` (single snapshot:
  no drift reference exists — the tag proves it).

## Rules the consumer inherits (non-negotiable)
- Skew levels are raw single-snapshot reads: no quintile badges, no
  "steep" labels without a universe (CL-31); percentiles wait on W4 store.
- Signed GEX regime badges stay BANNED (balanced-flow finding).
- Earnings hook: typed null + reason only (R1 — no Earnings Hub endpoint).

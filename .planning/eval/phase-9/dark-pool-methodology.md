# Dark-Pool Methodology + Honest Filtering — Agent 4

**Iron rule:** prints are LEVELS and SIZE evidence only. No side. No direction. No bull/bear labels.
Literature basis: Comerton-Forde & Putnins 2015 (blocks least informative); Zhu 2014 (informed prefer lit);
Buti-Rindi-Werner (effects conditional); FINRA ATS = volume + counts, no side, delayed (see claim-rule-map).

## 1. Data reality

- Free inputs: FINRA ATS weekly aggregates (delayed), Reg SHO daily (positioning context).
- No free real-time TRF prints → no live dark tape. Real-time TRF = paid-gate flag, never faked.
- Stored print fields: time, ticker, price, size, notional, sector, level, date.
  FORBIDDEN fields: side, aggressor, sweep, score, direction.

## 2. Best honest filtering (Top-N levels overlay)

- Min notional filter (default desk-set; UI exposes control; values below → hidden with count shown).
- Lookback windows: 30 / 45 / 90 / 180 days (UI selector).
- Top-N: 1 / 2 / 3 / 5 by total cluster notional within lookback.
- Sector filter (Unknown bucket when missing).
- Price-level clustering tolerance: default max(0.25% of price, 10 ticks), configurable; cluster fields:
  cluster_price, total_notional, print_count, latest_date (per-symbol only unless cross-symbol spec exists).
- Cluster strength = total_notional + print_count + recency (all three shown, none hidden in a blend).
- Level freshness: days-since-last-print shown on every level; stale (>lookback/2 with no refresh) dimmed.
- Confluence checklist (display alongside, never merged into a score): GEX/VEX zone, dealer-gamma sign,
  earnings proximity, Reg SHO short pressure, lit volume confirmation. Each check = present/absent line.
- Empty state: "No qualifying off-exchange prints in window — widen lookback or lower min notional."
- Paid-gate note: "Real-time TRF prints require a paid feed. Weekly ATS context shown with delay stamp."

## 3. Prohibited copy (exact strings — CI-grep these)

- "dark pool buying" · "dark pool selling" · "institutions are long here" · "bullish dark print" ·
  "bearish dark print" · any "confirmed buyer/seller" · "retail imbalance predicts" (without signed TAQ).

## 4. Allowed copy (exact strings)

- "large size transacted at this price" · "off-exchange print" · "level may act as reference" ·
  "no side is known" · "block liquidity event — execution footprint, no inferred direction" ·
  "Unsigned prints: activity and venue mix only — no buy/sell inference" (fixed footer on every dark surface).

## 5. Level label format

`DP $2.2B · 2026-05-15` + tooltip: "Off-exchange print. No side or direction is known.
Level shows where size transacted." Overlay shows price line + notional + print count + freshness only.

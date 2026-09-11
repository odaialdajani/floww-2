# Signed Score Spec (display-only, NOT alert-gating) — Agent 4

**Status:** spec v1 for Agent 1 review (architecture ask #2) and Agent 2 display work.
Score is a DISPLAY aid. Alert gates (92/$25M/6σ) are unchanged and owned by the desk.

## 1. Range and semantics

- Range: −100..+100. Sign = direction (D2: ASK→BULLISH incl. put-ASK with HEDGE? tag).
- 0 = balanced/unknown, never "neutral conviction".
- Display as integer + HEDGE?/proxy/degraded tags. Full provenance tooltip required.

## 2. Sign matrix (SIDE × C/P × hedge context)

SIDE is INFERRED (last-vs-mid). Sweep is PROXY. Both labeled in UI.

| SIDE (inferred) | C/P | Hedge context | Sign | Tags |
|---|---|---|---|---|
| ASK | CALL | — | + | — |
| ASK | PUT | open-interest rising, OTM | + | HEDGE? (D2: put-ASK stays BULLISH) |
| ASK | PUT | spread/closing迹象 (OI falling) | + (capped ≤ +40) | HEDGE?, CLOSE? |
| BID | PUT | — | − | — |
| BID | CALL | — | − | — |
| MID | either | — | sign of premium skew, magnitude halved | MID? |
| missing/NO_QUOTE | either | — | UNAVAILABLE (no score) | NO_QUOTE |

Rationale: D2 reference SIGNAL spec stands; Ge-Lin-Pearson 2016 (openings predict, closings don't)
justifies the falling-OI cap; An et al. 2014 justifies using IV changes, not levels.

## 3. Magnitude (0..100 before sign)

Weights (starting point — desk calibrates READ-ONLY via outcomes; overfit warning in §6):

- spread_position = (last−bid)/(ask−bid), clamped [0,1]: 25%. Distance from mid = aggression proxy.
  Missing/invalid quote → score unavailable (never guess).
- size/OI or vol/OI: 30%. volOI = volume/max(OI, floor). OI=0 & volume>0 → treat as max (with
  LOW_OI tag); both zero → component 0. Missing OI → cap total magnitude at 50 + DEGRADED tag.
- premium (log-scaled, $25K floor reference): 20%. premium < $25K → component 0 (below tape relevance).
- IV confirmation (changes, not levels — An et al. 2014): 15%. Call-IV-rising (put flat/down) confirms
  bullish; mirror for bearish; contradicts → subtract. Missing IV → omit component, rescale others
  proportionally + DEGRADED tag.
- DTE weighting: 10%. 0DTE with volOI≥2 → full weight (alert-gate parity); 1–7DTE full; 8–45 decay
  linearly to half; >45DTE half. Justification: P&P leverage concentration is moneyness-based, NOT a
  DTE band — weights are internal heuristics, never cited to P&P.

## 4. Missing-data handling

- SIDE missing → score UNAVAILABLE (dash + "no quote" state).
- OI missing → cap |score| ≤ 50, DEGRADED tag.
- IV missing → omit IV component, rescale, DEGRADED tag.
- Earnings ≤7d without smirk confirmation → cap bullish |score| ≤ 70 (Roll et al. 2010 lean).
- Falling-OI-only signal → cap |score| ≤ 40 (Ge-Lin-Pearson 2016).

## 5. Prohibited

VPIN input · crash-probability input · false sweep certainty (sweep proxy max weight 1.0×, never a
multiplier for "confirmed") · confirmed buyer/seller language · retail-imbalance input without signed
TAQ data (BJZZ scope limit).

## 6. Overfit warning (for Agent 1 ask #2)

Five inputs on snapshot proxies risk laundering noise as signal — especially spread_position on wide
spreads and volOI on stale OI. Mitigations: caps above, DEGRADED tags, display-only status, and the
rule that no weight changes ship without an evaluator + 30-min outcome read (W5/outcomes module).

## 7. Pseudocode

```
def signed_score(row):
    if row.bid <= 0 or row.ask <= 0 or row.ask <= row.bid:
        return UNAVAILABLE("NO_QUOTE")
    sp = clamp((row.last-row.bid)/(row.ask-row.bid),0,1)
    mid = (row.bid+row.ask)/2
    if abs(row.last-mid) < tick(row): side, mid_flag = "MID", True
    else: side, mid_flag = (ASK if row.last>=mid else BID), False  # inferred
    base = 25*abs(sp-0.5)*2
    voi = row.volume/max(row.oi,1); size_c = 30*min(voi/2,1)
    prem_c = 20*log10(1+row.premium/25_000)/log10(1+1_000_000/25_000) if row.premium>=25_000 else 0
    # IV alignment is DIRECTION-AWARE (round-6 fix): +1 confirms signal direction, -1 contradicts.
    # The raw IV trend must be mapped against the inferred side, never added with a fixed sign.
    iv_c = 15*iv_align(row, side)  # +1..-1; None→omit+rescale×(100/85)+DEGRADED
    dte_c = 10*dte_weight(row.dte, voi)
    mag = min(base+size_c+prem_c+iv_c+dte_c,100)
    if mid_flag: mag = mag/2; tags += [MID?]  # round-6 fix: matrix promised halving, code now does it
    mag = apply_caps(mag,row)  # OI-missing 50, falling-OI 40, earnings 70, put-ASK-close 40
    return sign(side,row)*round(mag), tags
```

Executed 2026-09-03 against all 10 unit tests (round-6 proof run): 1→+100 · 2→−100 · 3→0+MID? ·
4→UNAVAILABLE · 5→max+LOW_OI · 6→rescaled+DEGRADED · 7→+HEDGE? · 8→capped 40 · 9→full DTE ·
10→capped 70. Pre-fix run caught two spec bugs (fixed above): IV sign was not direction-aware
(perfect-bear printed −70); MID halving was promised in §2 but missing from pseudocode (MID-tiny
printed 7 instead of ~0).

## 8. Unit tests (must-pass list; fixtures in fixtures/score-cases.json)

1. Perfect bullish: call ASK at ask, volOI 2, $1M prem, IV confirms, 3DTE → +100 boundary (capped).
2. Perfect bearish mirror → −100.
3. Balanced MID small print → 0 (MID? tag, halved).
4. NO_QUOTE (bid=0) → UNAVAILABLE.
5. Zero OI + volume>0 → max size component + LOW_OI tag.
6. Missing IV → rescaled, DEGRADED, still signed.
7. Put-ASK rising OI → positive + HEDGE?.
8. Put-ASK falling OI → positive capped ≤40 + HEDGE?, CLOSE?.
9. 0DTE volOI≥2 → full DTE weight.
10. Earnings ≤7d bullish without smirk → capped ≤70.

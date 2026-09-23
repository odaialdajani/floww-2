# Solstice FROZEN validation protocol (T11/T28) — frozen 23 Sep 2026

Frozen means frozen: hypotheses, baselines, parameters, outcome definitions
and cost assumptions below must not change in response to held-out results.
Any change requires a new version + re-freeze note, never a silent edit.

## Hypotheses (falsifiable, in order)
- H1: raw-wall proximity + price confirmation beats price-only levels at
  equal eligible events after costs.
- H2: adding delta weighting improves H1 (same events, same costs).
- H3: adding window volume activity improves H2.
- H4: calibration-based sizing beats constant sizing on paired sessions.

## Baselines (solstice_ablation.run_ladder, abl.v1)
L0 price_only_reclaim → L1 raw_wall (+weak contemporaneous confirmation) →
L2 plus_delta (delta share ≥ 0.20) → L3 plus_window_activity (nonzero ΔV).
Confirmation is labeled WEAK until a price path exists (single snapshot).

## Parameters (frozen)
- Touch/near: 0.10% / 0.30% (TOUCH_PCT). Wall debounce: HOLD_S 60s,
  ACCEPT_S 120s (wall_interaction). Delta band research preset 0.40–0.60.
- Horizons: 60/180/300/900s (outcome.v1). Cost assumption: 20 bps of premium
  (explicit assumption — realized fills replace it when available).
- Splits: session-block walk-forward with 1-session embargo (solstice_labels).

## Outcomes (outcome.v1)
target_hit / stop_hit / no_touch / indeterminate / data_gap /
simultaneous_unknown (order unknown — never assumed profitable).

## Collection target
30–60 sessions is an initial collection target for engineering signal, NOT
proof of validity. Report: independent event counts (dedup repeated touches),
session-block uncertainty, regime coverage (positive/negative/transition days,
event days, thin sessions). SPY/QQQ first; SPX gated.

## Current inventory (23 Sep 2026)
- Recorded research snapshots: 2 (SPY + QQQ, single-session commissioning).
- Independent wall-encounter events with outcomes: 0.
- Status: collection phase. No validity claim exists or is implied.

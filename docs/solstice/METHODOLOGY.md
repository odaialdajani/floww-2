# Solstice METHODOLOGY (T14) — every visible label → formula/source

Formula version: gex.v2. Snapshot schema: 2. Evidence: solstice.evidence.v2.

| UI label | Formula / source | Unit | What it is NOT |
|---|---|---|---|
| Raw gross | Σu·N, u=Γ·m·S²×0.01 (gex_gross_v1) | USD/1% move | Not inventory |
| Raw net | Σc·u·N (gex_net_v1) | USD/1% move | Not dealer direction |
| Δ-wtd gross/net | Σu·N·|δ|, Σc·u·N·|δ| (dadgex_*) | USD/1% move | Not buying/selling |
| Activity | Σc·u·V (volume_gamma_v1) | USD/1% move | Turnover, not positioning |
| Window Δ | Σc·u·|δ|·ΔV(W) | USD/1% move | Not buy-minus-sell flow |
| King ★ (grid) | max |cell| in matrix | USD/1% move | Largest cell, not strongest wall |
| Strongest wall | max aggregate gross wall | USD/1% move | Aggregated scope |
| Regime sign | G_model(spot) under frozen OI/IV | sign | Never permits direction alone |
| Tap count | observed touches within 0.1% | count | Not a probability |
| Velocity mode | Δking/min over snapshots | strikes/min | Unknown until 2+ snapshots |
| LIVE badge | chain asof age ≤120s + usable quality | bool | Never socket presence |
| WAIT card | setupEligible=false + reason | state | A successful output |

Replay guide: open Replay → load manifest → step snapshot IDs in order.
Each step shows what was available then (received_at/known-at). Late data
never rewrites a step. Compare raw walls → activity at the wall → price
confirmation → candidate review; name the invalidation before the outcome.

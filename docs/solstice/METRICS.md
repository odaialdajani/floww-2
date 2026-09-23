# Solstice METRICS (gex.v2) — canonical registry

u_i = Γ_i · m_i · S² × 0.01  (USD per 1% move, per contract)

| Metric | Formula | Basis | Interpretation |
|---|---|---|---|
| gex_gross_v1 | Σ u N | OI | Wall discovery (no cancellation) |
| gex_net_v1 | Σ c u N | OI | Conventional call-minus-put proxy (not inventory) |
| dadgex_gross_v1 | Σ u N |δ| | OI Δ-weighted | Moneyness-weighted concentration |
| dadgex_net_v1 | Σ c u N |δ| | OI Δ-weighted | Weighted proxy (not flow) |
| volume_gamma_v1 | Σ c u V | VOLUME | Session turnover (not positioning) |
| window_dadgex_v1 | Σ c u |δ| ΔV(W) | VOLUME_WINDOW | Window activity (not buy/sell) |

Invariants (same valid set): |net| ≤ gross; |delta net| ≤ delta gross ≤ raw gross.
No bound |delta net| ≤ |raw net|. Signed put delta → abs() before put sign.
Missing delta/OI/volume → unavailable (never zero-fill, never substituted).
VEX/Vomma/Charm versioned separately; frozen ML S¹ scale untouched.

// Display metadata only. The backend registry owns formulas and numbers.
export const GEX_BASES = [
  { id: 'raw', label: 'Raw OI', units: 'USD/1% move · OI · gex_net_v1' },
  { id: 'delta', label: 'Δ-weighted OI', units: 'USD/1% move · dadgex_net_v1 — experimental weighting, not flow' },
  { id: 'session_delta_volume', label: 'Volume × |Δ|', units: 'USD/1% move · session_delta_volume_gamma_v1 — session turnover × |Δ|, not positioning' },
  { id: 'activity', label: 'Session volume Γ (no Δ)', units: 'USD/1% move · volume_gamma_v1 — session turnover without delta weighting, not positioning' },
];

export function gexBasisLabel(id) {
  return GEX_BASES.find(b => b.id === id)?.label || 'Unknown GEX basis';
}

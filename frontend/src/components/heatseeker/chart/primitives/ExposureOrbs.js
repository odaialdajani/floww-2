// B07 signed orbs: king_abs over measured nodes, ratio inclusive P, tie strike asc.
// Incomplete full-scope disables king/top-N/P; observed-subset has own identity.
// VANNA needs triple identity; parent formula alone rejected.
export function rankOrbs(nodes, { topN = null, pThreshold = null, scopeIdentity = 'full' } = {}) {
  const measured = (nodes || []).filter((n) => n && Number.isFinite(n.signed_value) && n.status !== 'unavailable');
  if (!measured.length) return { king: null, ranked: [], reason: 'unavailable' };
  if (scopeIdentity !== 'full' && scopeIdentity !== 'observed-subset') {
    return { king: null, ranked: [], reason: 'unknown-scope' };
  }
  const incomplete = (nodes || []).some((n) => n && n.status === 'incomplete');
  if (incomplete && scopeIdentity === 'full') {
    return { king: null, ranked: [], reason: 'incomplete-full-scope' };
  }
  const kingAbs = Math.max(...measured.map((n) => Math.abs(n.signed_value)));
  if (!(kingAbs > 0)) return { king: null, ranked: [], reason: 'measured-zero' };
  const withRatio = measured.map((n) => ({ ...n, ratio: Math.abs(n.signed_value) / kingAbs }));
  withRatio.sort((a, b) => Math.abs(b.signed_value) - Math.abs(a.signed_value) || a.strike - b.strike);
  let ranked = withRatio;
  if (pThreshold !== null) ranked = ranked.filter((n) => n.ratio >= pThreshold / 100 - 1e-12);
  if (topN !== null) ranked = ranked.slice(0, topN);
  return { king: withRatio[0], ranked, reason: 'ok' };
}
export function isVanna(channel) {
  return !!channel && channel.model === 'VEX_1VOLPT' && channel.basis === 'local-bs-vanna.v1' && channel.unit === 'USD-per-volpt';
}

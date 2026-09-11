// Pure — no React, no backend. Overview bar math: NetPrem, P/C, FIR, session label, RVOL honest-empty.
export function computeOverview(rows, opts = {}) {
  const list = Array.isArray(rows) ? rows : [];
  let callPrem = 0;
  let putPrem = 0;
  for (const r of list) {
    const p = Number(r?.premium ?? r?.notional ?? 0) || 0;
    const t = String(r?.type ?? '').toLowerCase();
    if (t.startsWith('c')) callPrem += p;
    else if (t.startsWith('p')) putPrem += p;
    else callPrem += p; // unknown type treated as call-side for totalling; still counted
  }
  const total = callPrem + putPrem;
  const netPremium = callPrem - putPrem; // signed lean for session label
  const pcRatio = callPrem > 0 ? putPrem / callPrem : null;
  const fir = total > 0 ? Math.abs(callPrem - putPrem) / total : null;
  let sessionLabel = 'Neutral';
  if (fir != null && fir >= 0.3) {
    if (netPremium > 0) sessionLabel = 'Bullish';
    else if (netPremium < 0) sessionLabel = 'Bearish';
  }
  // RVOL honest-empty until 20d baseline exists (PLAN.md: \"needs baseline\")
  const rvol = { value: null, state: 'needs_baseline', label: 'needs baseline' };
  return { netPremium, callPrem, putPrem, total, pcRatio, fir, sessionLabel, rvol };
}

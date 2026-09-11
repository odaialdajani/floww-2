// Pure JS — no React, no backend. ESM.
export function highlightFlags(row) {
  const vol = Number(row?.volume ?? row?.vol ?? row?.size ?? 0);
  const oi = Number(row?.oi ?? row?.openInterest ?? 0);
  const v = Number.isFinite(vol) ? vol : 0;
  const o = Number.isFinite(oi) ? oi : 0;
  if (o === 0 && v === 0) return { sizeGtOI: false, volGtOI: false };
  if (o === 0 && v > 0) return { sizeGtOI: true, volGtOI: true };
  const gt = v > o;
  return { sizeGtOI: gt, volGtOI: gt };
}

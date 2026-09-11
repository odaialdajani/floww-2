// Pure JS — no React, no backend. ESM.
export function strategyBadge(row) {
  if (!row || typeof row !== 'object') return null;
  const legs = row.legs;
  if (Array.isArray(legs)) {
    if (legs.length >= 2) return 'MULTI_LEG';
    if (legs.length === 1) {
      const t = legs[0]?.type;
      return t ? String(t).toUpperCase() : null;
    }
    return null;
  }
  const t = row.type ?? row.legType ?? row.optionType ?? row.side;
  return t ? String(t).toUpperCase() : null;
}

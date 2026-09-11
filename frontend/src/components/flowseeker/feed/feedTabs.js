// Pure JS — no React, no backend. ESM.

const VALID_CAPS = new Set([50, 100, 250, 500]);

export function validateTabs(tabs, kind = 'live') {
  if (!Array.isArray(tabs)) return { valid: false, reason: 'tabs must be an array' };
  const max = kind === 'scanner' ? 5 : 10;
  if (tabs.length > max) return { valid: false, reason: `${kind} tabs exceed max ${max} (got ${tabs.length})` };
  if (tabs.length === 0) return { valid: false, reason: 'at least one tab required' };
  return { valid: true };
}

export function tickerScopeFilter(rows, scope) {
  if (!Array.isArray(rows)) return [];
  if (scope == null || scope === 'ALL') return rows;
  const s = String(scope).trim();
  if (!s || s === 'ALL') return rows;
  if (s.startsWith('!')) {
    const excl = s.slice(1).trim().toUpperCase();
    if (!excl) return rows;
    return rows.filter((r) => String(r.under || r.ticker || '').toUpperCase() !== excl);
  }
  const ticker = s.toUpperCase();
  return rows.filter((r) => String(r.under || r.ticker || '').toUpperCase() === ticker);
}

export function resultsCap(rows, cap) {
  if (!Array.isArray(rows)) return [];
  if (!VALID_CAPS.has(cap)) return rows;
  return rows.slice(0, cap);
}

export function sortRows(rows, sort) {
  if (!Array.isArray(rows)) return [];
  const copy = [...rows];
  // Support both string ('Premium'/'Size') and object ({key, dir}) callers
  const key = typeof sort === 'string' ? sort : (sort?.key ?? 'time');
  const dir = typeof sort === 'string' ? -1 : (sort?.dir === 'asc' ? 1 : -1);
  const k = String(key).toLowerCase();
  if (k === 'premium') {
    // $25K floor — filter then sort by premium desc/asc
    const floored = copy.filter((r) => (Number(r.premium) || 0) >= 25000);
    floored.sort((a, b) => dir * ((Number(a.premium) || 0) - (Number(b.premium) || 0)));
    return floored;
  }
  if (k === 'size' || k === 'volume') {
    // 150 floor — filter then sort by volume desc/asc
    const floored = copy.filter((r) => (Number(r.vol ?? r.volume ?? 0) || 0) >= 150);
    floored.sort((a, b) => dir * ((Number(a.vol ?? a.volume ?? 0) || 0) - (Number(b.vol ?? b.volume ?? 0) || 0)));
    return floored;
  }
  // Time: timestamp desc — prefer firstSeen, then timestamp, then 0
  return copy.sort((a, b) => {
    const ta = a.firstSeen ?? a.timestamp ?? a.seen ?? 0;
    const tb = b.firstSeen ?? b.timestamp ?? b.seen ?? 0;
    return dir * ((tb || 0) - (ta || 0));
  });
}

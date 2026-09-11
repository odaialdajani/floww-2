// Pure — filter state, subtractive apply, widen actions. No React.
import { equityType as _equityType } from '../context/sectorMap.js';

export function defaultFilterState() {
  return {
    equityType: { stocks: true, etfs: true, indices: true },
    sweepsOnly: false,
    side: { BID: true, MID: true, ASK: true },
    otm: false,
    itm: false,
    dte0: false,
    opexOnly: false,
    strikeRange: { min: null, max: null },
    oiGrowth: { min: 0 },
    sentiment: { contract: [-100, 100], chain: [-100, 100] },
    absScore: false,
    minPremium: 0,
    minScore: 0,
    dteBand: null, // e.g. '0-7' or null for all
  };
}

// Helpers — only use fields that exist on rows
function isSweep(r) {
  const c = String(r.classification ?? r.ftype ?? '').toLowerCase();
  return c === 'sweep';
}
function spreadSide(r) {
  // row may have side from spreadPosition or raw SIDE field
  return String(r.side ?? r.SIDE ?? '').toUpperCase();
}
function isOpexWeek(exp) {
  if (!exp) return false;
  const d = new Date(exp);
  if (Number.isNaN(d.getTime())) return false;
  // 3rd Friday of month
  const y = d.getUTCFullYear();
  const m = d.getUTCMonth();
  let friCount = 0;
  for (let day = 1; day <= 31; day++) {
    const t = new Date(Date.UTC(y, m, day));
    if (t.getUTCMonth() !== m) break;
    if (t.getUTCDay() === 5) {
      friCount++;
      if (friCount === 3) {
        const thirdFri = Date.UTC(y, m, day);
        const expDay = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
        // within Mon-Fri of that week
        return Math.abs(expDay - thirdFri) <= 4 * 86400000;
      }
    }
  }
  return false;
}

export function applyFilters(rows, filters = defaultFilterState()) {
  const beforeCount = (rows || []).length;
  let out = [...(rows || [])];

  // Equity-type triple toggle (subtractive)
  const et = filters.equityType;
  if (et && (!et.stocks || !et.etfs || !et.indices)) {
    out = out.filter((r) => {
      const t = _equityType(r.ticker ?? r.under ?? '');
      if (t === 'etf' && !et.etfs) return false;
      if (t === 'index' && !et.indices) return false;
      if (t === 'stock' && !et.stocks) return false;
      return true;
    });
  }
  // Sweeps-only chip (label as proxy if needed — display concern, not filter)
  if (filters.sweepsOnly) out = out.filter(isSweep);
  // Side chips (BID/MID/ASK) — only if row has a side field; otherwise pass through
  if (filters.side) {
    const s = filters.side;
    const anyOff = !s.BID || !s.MID || !s.ASK;
    if (anyOff) {
      out = out.filter((r) => {
        const side = spreadSide(r);
        if (!side || side === 'NO_QUOTE' || side === 'LOCKED') return true; // no-quote/locked rows never filtered by side
        return !!s[side];
      });
    }
  }
  // OTM / ITM / 0DTE toggles
  if (filters.otm) out = out.filter((r) => r.otm != null && r.otm > 0);
  if (filters.itm) out = out.filter((r) => r.otm != null && r.otm < 0);
  if (filters.dte0) out = out.filter((r) => Number(r.dte) === 0);
  if (filters.opexOnly) out = out.filter((r) => isOpexWeek(r.exp ?? r.expiration));
  // Strike range
  if (filters.strikeRange && (filters.strikeRange.min != null || filters.strikeRange.max != null)) {
    const mn = filters.strikeRange.min;
    const mx = filters.strikeRange.max;
    out = out.filter((r) => {
      const k = Number(r.strike);
      if (!Number.isFinite(k)) return false;
      if (mn != null && k < mn) return false;
      if (mx != null && k > mx) return false;
      return true;
    });
  }
  // OI-growth — only if row has oiChg or oi field; otherwise skip (fixture-first)
  if (filters.oiGrowth && Number(filters.oiGrowth.min) > 0) {
    const thr = Number(filters.oiGrowth.min);
    out = out.filter((r) => {
      const pct = r.oiChg?.pct ?? r.oiGrowth ?? null;
      if (pct == null) return true; // no data => don't filter
      return pct >= thr;
    });
  }
  // Premium / score floors (if set)
  if (Number(filters.minPremium) > 0) out = out.filter((r) => (Number(r.premium) || 0) >= Number(filters.minPremium));
  if (Number(filters.minScore) > 0) {
    const thr = Number(filters.minScore);
    const useAbs = !!filters.absScore;
    out = out.filter((r) => {
      const s = Number(r.score ?? r._conv ?? 0) || 0;
      return useAbs ? Math.abs(s) >= thr : s >= thr;
    });
  }

  return { rows: out, beforeCount, afterCount: out.length };
}

export function widenActions(filters = {}) {
  const acts = [];
  if (Number(filters.minPremium) > 0) acts.push({ label: 'Lower premium min', action: 'lower_premium' });
  if (filters.equityType && !filters.equityType.etfs) acts.push({ label: 'Enable ETFs', action: 'enable_etfs' });
  if (filters.sweepsOnly) acts.push({ label: 'Clear sweep-only', action: 'clear_sweep' });
  if (Number(filters.minScore) > 0) acts.push({ label: 'Lower score threshold', action: 'lower_score' });
  if (filters.dteBand) acts.push({ label: 'Clear DTE band', action: 'clear_dte' });
  if (filters.dte0 || filters.opexOnly) acts.push({ label: 'Clear DTE filter', action: 'clear_dte' });
  if (!acts.length) acts.push({ label: 'Reset filters', action: 'reset' });
  return acts;
}

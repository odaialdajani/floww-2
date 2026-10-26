// Market-local money formatting (owner 13:40 desktop composition): the
// comparison cells move from fmtK's long grouped-thousands strings
// ("$-918,926.0K", "$9,469.8M") to HUMAN K/M/B scales at appropriate
// thresholds with signs and units — while the EXACT source value stays
// reachable: the cell title, the inspector and the provenance detail all
// carry exactMoney(v) verbatim. Never tooltip-only precision.
//
// Gap rule preserved: null/undefined/NaN render empty — never "$0", never a
// fabricated value.

const GROUP0 = (n) => String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
const GROUP = (n) => {
  const s = n.toFixed(2);
  const dot = s.indexOf('.');
  const int = dot === -1 ? s : s.slice(0, dot);
  const frac = dot === -1 ? '' : s.slice(dot);
  return int.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + frac;
};

// The compact human scale: |v| < 1e3 exact · < 1e6 K · < 1e9 M · else B,
// one fraction digit, sign always leading, unit always explicit.
export function marketMoney(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return '';
  const sign = v < 0 ? '-' : '';
  const a = Math.abs(v);
  if (a < 1000) return `${sign}$${Math.round(a)}`;
  if (a < 1e6) return `${sign}$${(a / 1e3).toFixed(1)}K`;
  if (a < 1e9) return `${sign}$${(a / 1e6).toFixed(1)}M`;
  return `${sign}$${(a / 1e9).toFixed(1)}B`;
}

// The EXACT source value: full precision, en-US grouping, sign, unit.
// Two fraction digits only when the source carries them; integers stay
// integer-exact (the source value verbatim, never rounded).
export function exactMoney(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return '';
  const sign = v < 0 ? '-' : '';
  const a = Math.abs(v);
  return Number.isInteger(a) ? `${sign}$${GROUP0(a)}` : `${sign}$${GROUP(a)}`;
}

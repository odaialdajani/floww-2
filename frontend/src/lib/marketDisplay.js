export const formatStrike = value => typeof value === 'number' && Number.isFinite(value)
  ? value.toLocaleString(undefined, {maximumFractionDigits: 3}) : '—';

export const formatGreek = value => typeof value === 'number' && Number.isFinite(value)
  ? value === 0 ? '0' : Math.abs(value) < 0.0001 ? value.toExponential(2) : value.toFixed(4) : '—';

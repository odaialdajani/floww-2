// Pure JS — no React, no backend. ESM.
export function earningsProximity(ticker, earningsDateStr, now = Date.now()) {
  if (!earningsDateStr) return { daysTo: null, label: '—', state: 'missing' };
  const d = new Date(earningsDateStr);
  if (Number.isNaN(d.getTime())) return { daysTo: null, label: '—', state: 'unknown' };
  const msPerDay = 86400000;
  const startOfEarnings = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
  const nowDate = new Date(now);
  const startOfNow = Date.UTC(nowDate.getUTCFullYear(), nowDate.getUTCMonth(), nowDate.getUTCDate());
  const daysTo = Math.round((startOfEarnings - startOfNow) / msPerDay);
  let label;
  if (daysTo === 0) label = 'Today';
  else if (daysTo === 1) label = 'Tomorrow';
  else if (daysTo > 1) label = `in ${daysTo}d`;
  else if (daysTo === -1) label = 'Yesterday';
  else label = `${Math.abs(daysTo)}d ago`;
  return { daysTo, label, state: 'has_date' };
}

// G6 bar-distributed volume profile (explicit approximation, mirrors
// backend chart_volume_profile.py). Overlap pro-rata allocation; POC ties
// down; VA expansion ties up; sparse stop with attained fraction.
function barVolume(bar) {
  const v = bar?.volume;
  return typeof v === 'number' && Number.isFinite(v) && v >= 0 ? v : null;
}
export function volumeProfile(bars, { rows = 200, valueAreaPct = 0.70 } = {}) {
  const list = Array.isArray(bars) ? bars : [];
  if (rows < 1 || !list.length) return { status: 'unavailable', reason: 'no input' };
  const lows = [], highs = [];
  for (const bar of list) {
    const { low, high } = bar || {};
    if (typeof low !== 'number' || typeof high !== 'number' || !Number.isFinite(low) || !Number.isFinite(high)) {
      return { status: 'unavailable', reason: 'bad prices' };
    }
    if (barVolume(bar) === null) return { status: 'unavailable', reason: 'missing volume' };
    lows.push(low); highs.push(high);
  }
  const lo = Math.min(...lows), hi = Math.max(...highs);
  if (!(hi > lo)) {
    const total = list.reduce((s, b) => s + barVolume(b), 0);
    return { status: 'ok', rows: [{ price: lo, volume: total }], poc: { price: lo, volume: total },
      value_area: { low: lo, high: lo, attained: 1 }, total_volume: total, approximation: 'bar-range' };
  }
  const width = (hi - lo) / rows, vols = new Array(rows).fill(0);
  list.forEach((bar, bi) => {
    const v = barVolume(bar), span = highs[bi] - lows[bi];
    if (span <= 0) {
      vols[Math.min(rows - 1, Math.max(0, Math.floor((lows[bi] - lo) / width)))] += v;
      return;
    }
    for (let i = 0; i < rows; i += 1) {
      const overlap = Math.min(highs[bi], lo + (i + 1) * width) - Math.max(lows[bi], lo + i * width);
      if (overlap > 0) vols[i] += (v * overlap) / span;
    }
  });
  const total = vols.reduce((s, v) => s + v, 0);
  if (!(total > 0)) return { status: 'unavailable', reason: 'zero volume' };
  const peak = vols.indexOf(Math.max(...vols));
  const target = total * valueAreaPct;
  let loI = peak, hiI = peak, acc = vols[peak];
  while (acc < target) {
    const up = hiI + 1 < rows ? vols[hiI + 1] : null;
    const dn = loI - 1 >= 0 ? vols[loI - 1] : null;
    if (up === null && dn === null) break;
    if (up === null) { loI -= 1; acc += dn; }
    else if (dn === null) { hiI += 1; acc += up; }
    else if (up >= dn) { hiI += 1; acc += up; }
    else { loI -= 1; acc += dn; }
    if (up === 0 && dn === 0) break;
  }
  return { status: 'ok',
    rows: vols.map((volume, i) => ({ price: lo + (i + 0.5) * width, volume })).filter((r) => r.volume > 0),
    poc: { price: lo + (peak + 0.5) * width, volume: vols[peak] },
    value_area: { low: lo + loI * width, high: lo + (hiI + 1) * width, attained: acc / total },
    total_volume: total, approximation: 'bar-range' };
}

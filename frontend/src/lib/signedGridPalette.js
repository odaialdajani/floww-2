// Presentation only: the Screener lattice's colors and magnitude thresholds.
// Backend values, units, coverage and sign assumptions keep their original owners.
export const NEGATIVE_HATCH = 'repeating-linear-gradient(-45deg, rgba(0, 0, 0, 0.28) 0 2px, transparent 2px 6px)';
const COLORS = {
  neutral: '#191919',
  positive: ['#191919', '#3a3226', '#6b5433', '#96713f'],
  negative: ['#191919', '#232032', '#37306b', '#544a9e'],
};
function styleFor(hex, negative = false) {
  const channels = hex.slice(1).match(/../g).map(v => parseInt(v, 16));
  const linear = channels.map(v => {
    const s = v / 255;
    return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  const luminance = linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
  const white = 1.05 / (luminance + 0.05), black = (luminance + 0.05) / 0.05;
  return Object.freeze({
    background: `rgb(${channels.join(', ')})`,
    backgroundImage: negative ? NEGATIVE_HATCH : 'none',
    foreground: black > white ? '#000' : '#fff',
    contrast: Math.max(black, white),
  });
}
// Prepare seven styles once, rather than running color math for every cell.
const NEUTRAL = styleFor(COLORS.neutral);
const POSITIVE = COLORS.positive.map(hex => styleFor(hex));
const NEGATIVE = COLORS.negative.map((hex, i) => styleFor(hex, i > 0));

export function signedCellPalette(value, extent) {
  if (!Number.isFinite(value) || value === 0 || !Number.isFinite(extent) || extent <= 0) return NEUTRAL;
  const strength = Math.abs(value) / extent;
  const level = strength > 0.66 ? 3 : strength > 0.33 ? 2 : strength > 0.02 ? 1 : 0;
  return (value < 0 ? NEGATIVE : POSITIVE)[level];
}

// Compatibility for the analytical range's symmetric, zero-anchored scale.
export function cellPalette(t) {
  return signedCellPalette(Number.isFinite(t) ? Math.max(0, Math.min(1, t)) * 2 - 1 : null, 1);
}

// B17 presets: starred > active > built-in per family, explicit Update only,
// 50 quota, owner isolation (checked server-side), dirty tracking.
import { toolFamily } from './toolRegistry';

export const PRESET_CAP = 50;
export function presetForNew({ starred, active }) {
  return starred || active || 'built-in';
}
export function isDirty(drawing, preset) {
  return JSON.stringify(drawing?.style) !== JSON.stringify(preset?.style);
}
export function applyPreset(drawing, preset) {
  // B17 preset manager: applying records the LINK (the drawing now tracks the
  // preset it came from) so the dirty dot has an honest reference. The pinned
  // contract is unchanged — style is copied wholesale and dirty clears.
  return { ...drawing, style: { ...preset.style }, dirty: false, presetId: preset?.id ?? null };
}

// ── CHART-C130: the full per-family preset style schema ──────────────────
// Every field listed here is a SUPPORTED style field for that family. The
// schema is closed per family: sanitizePresetStyle drops fields that do not
// belong, which is what makes "no generic color swatch override for per-level
// Fib colors" hold — 'color' on fib is the trendline/extension color only;
// the per-level colors live in levelColors and are never overridden by it.
export const PRESET_STYLE_FIELDS = {
  line: ['color', 'width', 'dash', 'extendLeft', 'extendRight', 'showLabels'], // trend, horizontal, horizontal-ray, vertical
  shape: ['color', 'width', 'dash', 'fillOpacity'],                            // rectangle, arrow
  free: ['color', 'width'],                                                     // brush
  fib: ['color', 'width', 'dash', 'ratios', 'levelColors', 'showLevels', 'fillOpacity', 'extensions', 'trendline', 'labels', 'logScale', 'reverse'],
  label: ['color', 'fontSize'],                                                 // text
  risk: ['color', 'width', 'dash', 'fillOpacity', 'side'],                      // analysis box, never broker intent
};

const FIB_COLORS = ['#7fa6c0', '#e3c16a', '#5ec986', '#d65656', '#c4a1ef', '#5a9bd4', '#9a9a9a'];
const CANONICAL_FIB_LEVELS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1]; // matches advancedTools.FIB_LEVELS

// Deep copies on every access — callers never share mutable defaults.
export const DEFAULT_PRESET_STYLE = {
  line: () => ({ color: '#7fa6c0', width: 1, dash: false, extendLeft: false, extendRight: false, showLabels: false }),
  shape: () => ({ color: '#5ec986', width: 1, dash: false, fillOpacity: 0.2 }),
  free: () => ({ color: '#c4a1ef', width: 2 }),
  fib: () => ({
    color: '#7fa6c0', width: 1, dash: false,
    ratios: CANONICAL_FIB_LEVELS.slice(),
    levelColors: FIB_COLORS.slice(0, CANONICAL_FIB_LEVELS.length),
    showLevels: CANONICAL_FIB_LEVELS.map(() => true),
    fillOpacity: 0.15,
    extensions: false, trendline: true, labels: false, logScale: false, reverse: false,
  }),
  label: () => ({ color: '#e3c16a', fontSize: 11 }),
  risk: () => ({ color: '#d65656', width: 1, dash: true, fillOpacity: 0.12, side: 'long' }),
};
export function defaultStyleForTool(toolId) {
  const make = DEFAULT_PRESET_STYLE[toolFamily(toolId)];
  return make ? make() : {};
}

// Keep only the supported fields for the tool's family. Falsey SUPPORTED
// values (false, 0, null) are preserved — C091 "preserve false options".
// C130 fib normalization: an older writer or hand-edited store can leave
// levelColors/showLevels shorter (or longer) than ratios — pad from the
// canonical palette / the visible-by-default convention and trim extras so
// a renderer never reads undefined or invents levels. Surviving user values
// are kept in place.
const CANONICAL_FIB_COLORS = ['#7fa6c0', '#e3c16a', '#5ec986', '#d65656', '#c4a1ef', '#5a9bd4', '#9a9a9a'];
function normalizeFibArrays(style) {
  const out = { ...style };
  const n = Array.isArray(out.ratios) ? out.ratios.length : 0;
  if (n > 0) {
    if (Array.isArray(out.levelColors) && out.levelColors.length !== n) {
      const colors = out.levelColors.slice(0, n);
      while (colors.length < n) colors.push(CANONICAL_FIB_COLORS[colors.length % CANONICAL_FIB_COLORS.length]);
      out.levelColors = colors;
    }
    if (Array.isArray(out.showLevels) && out.showLevels.length !== n) {
      const visible = out.showLevels.slice(0, n);
      while (visible.length < n) visible.push(true); // visible-by-default convention
      out.showLevels = visible;
    }
  }
  return out;
}
export function sanitizePresetStyle(toolId, style) {
  const family = toolFamily(toolId);
  if (!family) return null; // unsupported tool — caller refuses upstream
  const fields = PRESET_STYLE_FIELDS[family];
  const source = family === 'fib' ? normalizeFibArrays(style || {}) : (style || {});
  const out = {};
  for (const key of Object.keys(source)) {
    if (fields.includes(key)) out[key] = source[key];
  }
  return out;
}
export function styleFieldsForTool(toolId) {
  const family = toolFamily(toolId);
  return family ? PRESET_STYLE_FIELDS[family].slice() : [];
}

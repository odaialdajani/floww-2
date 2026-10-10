// B17 presets: starred > active > built-in per family, explicit Update only,
// 50 quota, owner isolation (checked server-side), dirty tracking.
export const PRESET_CAP = 50;
export function presetForNew({ starred, active }) {
  return starred || active || 'built-in';
}
export function isDirty(drawing, preset) {
  return JSON.stringify(drawing?.style) !== JSON.stringify(preset?.style);
}
export function applyPreset(drawing, preset) {
  return { ...drawing, style: { ...preset.style }, dirty: false };
}

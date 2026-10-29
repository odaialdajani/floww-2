// B17 drawing PRESET MANAGER — pure operations, no React, no storage.
// The visible manager UI is DrawingRail's optional preset section; the caller
// (ChartWorkspace/PriceNodeHistory, H1-owned) owns state and wires these ops
// through the callbacks documented in Hermes-2-CONTINUATION.md.
//
// CHART-C091: named/starred/active presets, cap 50, false options preserved.
// CHART-C129: dirty dot + explicit Update only — a preset's style changes
//   ONLY through updatePresetStyle; style edits on a drawing NEVER autosave;
//   updating a preset never restyles existing drawings.
// CHART-C130: styles are sanitized against the per-family schema.
// Isolation: every operation is scoped to the list it is given; scopes are
// separated at the persistence layer (presetPersistence.js).
import { PRESET_CAP, presetForNew, isDirty, applyPreset, defaultStyleForTool, sanitizePresetStyle } from './presetSchema';
import { isSupportedTool, toolFamily } from './toolRegistry';

let seq = 0;
function newId() {
  seq += 1;
  return 'preset-' + Date.now().toString(36) + '-' + seq;
}
const isBuiltIn = (p) => p && p.kind === 'built-in';

// The built-in per-tool default preset (presetForNew's fallback tier).
export function builtInPresetFor(toolId) {
  if (!isSupportedTool(toolId)) return null;
  return {
    id: 'builtin:' + toolId, name: 'Built-in ' + toolId, tool: toolId,
    kind: 'built-in', starred: false, active: false,
    style: defaultStyleForTool(toolId),
  };
}

// User presets recorded for a tool (the caller may merge the built-in when
// displaying the full ladder).
export function presetsForTool(list, toolId) {
  return (Array.isArray(list) ? list : []).filter((p) => p && p.tool === toolId);
}

// C091: which preset a NEW drawing of this tool gets — starred > active >
// built-in, resolving presetForNew's tier order to an actual preset object.
export function defaultPresetFor(list, toolId) {
  if (!isSupportedTool(toolId)) return null;
  const forTool = presetsForTool(list, toolId);
  const starred = forTool.find((p) => p.starred);
  const active = forTool.find((p) => p.active);
  const tier = presetForNew({ starred: starred?.id, active: active?.id });
  if (tier === starred?.id) return starred;
  if (tier === active?.id) return active;
  return builtInPresetFor(toolId);
}

// C091 create: explicit name, supported tool, schema-sanitized style, cap 50.
// Refusals return { ok:false, error } and never a partial list.
export function createPreset(list, { name, tool, style }) {
  const clean = Array.isArray(list) ? list : [];
  const trimmed = typeof name === 'string' ? name.trim() : '';
  if (!trimmed) return { ok: false, error: 'preset name required' };
  if (!isSupportedTool(tool)) return { ok: false, error: 'unsupported tool: ' + tool };
  if (clean.some((p) => p && p.name && p.name.toLowerCase() === trimmed.toLowerCase())) {
    return { ok: false, error: 'preset name already exists: ' + trimmed };
  }
  if (clean.length >= PRESET_CAP) {
    return { ok: false, error: 'preset cap reached (' + PRESET_CAP + ')' };
  }
  const sanitized = sanitizePresetStyle(tool, style || {});
  if (sanitized === null) return { ok: false, error: 'unsupported tool: ' + tool };
  const preset = { id: newId(), name: trimmed, tool, kind: 'user', starred: false, active: false, style: sanitized };
  return { ok: true, list: [...clean, preset], preset };
}

// C129 EXPLICIT Update: the ONLY style mutation on a preset. Built-ins refuse.
// Returns a new list; no drawing anywhere is touched by this operation.
export function updatePresetStyle(list, id, style) {
  const clean = Array.isArray(list) ? list : [];
  const target = clean.find((p) => p && p.id === id);
  if (!target) return { ok: false, error: 'preset not found: ' + id };
  if (isBuiltIn(target)) return { ok: false, error: 'built-in presets cannot be updated' };
  const sanitized = sanitizePresetStyle(target.tool, style || {});
  if (sanitized === null) return { ok: false, error: 'unsupported tool: ' + target.tool };
  return { ok: true, list: clean.map((p) => (p.id === id ? { ...p, style: sanitized } : p)) };
}

export function renamePreset(list, id, name) {
  const clean = Array.isArray(list) ? list : [];
  const trimmed = typeof name === 'string' ? name.trim() : '';
  const target = clean.find((p) => p && p.id === id);
  if (!target) return { ok: false, error: 'preset not found: ' + id };
  if (isBuiltIn(target)) return { ok: false, error: 'built-in presets cannot be renamed' };
  if (!trimmed) return { ok: false, error: 'preset name required' };
  if (clean.some((p) => p !== target && p.name && p.name.toLowerCase() === trimmed.toLowerCase())) {
    return { ok: false, error: 'preset name already exists: ' + trimmed };
  }
  return { ok: true, list: clean.map((p) => (p.id === id ? { ...p, name: trimmed } : p)) };
}

export function deletePreset(list, id) {
  const clean = Array.isArray(list) ? list : [];
  const target = clean.find((p) => p && p.id === id);
  if (!target) return { ok: false, error: 'preset not found: ' + id };
  if (isBuiltIn(target)) return { ok: false, error: 'built-in presets cannot be deleted' };
  return { ok: true, list: clean.filter((p) => p.id !== id) };
}

// CHART-C131 "built-in reset": a USER preset's style returns to the family
// built-in default. Built-ins refuse — they ARE the default. Pure op: like
// every manager operation it touches the preset list only, never drawings.
export function resetPresetStyleToBuiltIn(list, id) {
  const clean = Array.isArray(list) ? list : [];
  const target = clean.find((p) => p && p.id === id);
  if (!target) return { ok: false, error: 'preset not found: ' + id };
  if (isBuiltIn(target)) return { ok: false, error: 'built-in presets are already the default' };
  return { ok: true, list: clean.map((p) => (p.id === id ? { ...p, style: defaultStyleForTool(p.tool) } : p)) };
}

// Star is multi (any number starred); the starred tier wins per tool.
// Built-ins refuse — they are the fallback tier, not user-managed state
// (symmetric with setActivePreset), so a caller-materialized built-in can
// never accumulate a phantom star that vanishes on the next regeneration.
export function toggleStar(list, id) {
  const clean = Array.isArray(list) ? list : [];
  const target = clean.find((p) => p && p.id === id);
  if (!target) return { ok: false, error: 'preset not found: ' + id };
  if (isBuiltIn(target)) return { ok: false, error: 'built-in presets cannot be starred' };
  return { ok: true, list: clean.map((p) => (p.id === id ? { ...p, starred: !p.starred } : p)) };
}

// C091: active is single per tool — activating one deactivates the others of
// that tool. Built-ins cannot be active (they are the fallback tier).
export function setActivePreset(list, id) {
  const clean = Array.isArray(list) ? list : [];
  const target = clean.find((p) => p && p.id === id);
  if (!target) return { ok: false, error: 'preset not found: ' + id };
  if (isBuiltIn(target)) return { ok: false, error: 'built-in presets cannot be the active preset' };
  return {
    ok: true,
    list: clean.map((p) => (p.tool === target.tool ? { ...p, active: p.id === id } : p)),
  };
}

// C129 dirty dot: the linked preset (drawing.presetId) when the drawing's
// style has drifted from it. Null when clean or not linked.
export function dirtyPresetFor(drawing, list) {
  const clean = Array.isArray(list) ? list : [];
  const linked = clean.find((p) => p && p.id === drawing?.presetId);
  if (!linked) return null;
  return isDirty(drawing, linked) ? linked : null;
}

// Apply to a drawing: copies the preset style wholesale, clears dirty and
// records the link (presetSchema.applyPreset).
export function applyPresetToDrawing(drawing, preset) {
  return applyPreset(drawing, preset);
}

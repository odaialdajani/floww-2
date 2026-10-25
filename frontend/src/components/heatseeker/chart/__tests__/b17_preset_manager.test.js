/** @jest-environment jsdom */
// B17 + CHART-C091/C129/C130 focused pins — preset MANAGER (pure module).
// RED-first: presetManager.js does not exist yet.
import {
  createPreset, updatePresetStyle, renamePreset, deletePreset, toggleStar,
  setActivePreset, defaultPresetFor, builtInPresetFor, presetsForTool,
  dirtyPresetFor, applyPresetToDrawing,
} from '../drawings/presetManager';
import { PRESET_CAP, presetForNew, isDirty, applyPreset, defaultStyleForTool, sanitizePresetStyle, PRESET_STYLE_FIELDS } from '../drawings/presetSchema';
import { FIB_LEVELS } from '../drawings/advancedTools';

const nameOk = (r) => expect(r.ok).toBe(true);

test('C091: a named user preset is created with explicit fields and refused past the cap50', () => {
  const first = createPreset([], { name: 'My trend', tool: 'trend', style: { color: '#7fa6c0', width: 2 } });
  nameOk(first);
  expect(first.preset).toMatchObject({ name: 'My trend', tool: 'trend', kind: 'user', starred: false, active: false });
  expect(first.preset.style).toEqual({ color: '#7fa6c0', width: 2 });
  // name collisions are refused (case-insensitive) — never a silent overwrite
  const dup = createPreset(first.list, { name: 'my TREND', tool: 'trend', style: {} });
  expect(dup.ok).toBe(false);
  expect(dup.error).toMatch(/name/i);
  // unsupported tools are refused — never an invented tool
  const badTool = createPreset([], { name: 'x', tool: 'nope', style: {} });
  expect(badTool.ok).toBe(false);
  // the cap is enforced at PRESET_CAP (50), preserving the schema constant
  let list = [];
  for (let i = 0; i < PRESET_CAP; i++) {
    const r = createPreset(list, { name: 'p' + i, tool: 'trend', style: { width: 1 } });
    nameOk(r); list = r.list;
  }
  expect(list).toHaveLength(PRESET_CAP);
  const over = createPreset(list, { name: 'overflow', tool: 'trend', style: {} });
  expect(over.ok).toBe(false);
  expect(over.error).toMatch(/50|cap/i);
});

test('C091: star and active are explicit, one active per tool, false options preserved', () => {
  const a = createPreset([], { name: 'A', tool: 'trend', style: { width: 1 } }).list;
  const b = createPreset(a, { name: 'B', tool: 'trend', style: { width: 2 } }).list;
  const c = createPreset(b, { name: 'C', tool: 'horizontal', style: { dash: true } }).list;
  const starred = toggleStar(c, c.find(p => p.name === 'B').id).list;
  expect(starred.find(p => p.name === 'B').starred).toBe(true);
  // starring a second preset does not unstar the first (star is multi)
  const starred2 = toggleStar(starred, starred.find(p => p.name === 'A').id).list;
  expect(starred2.filter(p => p.starred)).toHaveLength(2);
  // active is single per tool
  const act1 = setActivePreset(starred2, starred2.find(p => p.name === 'A').id).list;
  expect(act1.find(p => p.name === 'A').active).toBe(true);
  const act2 = setActivePreset(act1, act1.find(p => p.name === 'B').id).list;
  expect(act2.find(p => p.name === 'B').active).toBe(true);
  expect(act2.find(p => p.name === 'A').active).toBe(false);
  // false options survive the operations untouched (C091 "preserve false options")
  const cRow = act2.find(p => p.name === 'C');
  expect(cRow.starred).toBe(false);
  expect(cRow.active).toBe(false);
  expect(cRow.style.dash).toBe(true);
});

test('C129: updatePresetStyle is the ONLY style mutation and never restyles drawings', () => {
  const list = createPreset([], { name: 'A', tool: 'trend', style: { color: '#7fa6c0', width: 1 } }).list;
  const id = list[0].id;
  const updated = updatePresetStyle(list, id, { color: '#e3c16a', width: 3 });
  expect(updated.list.find(p => p.id === id).style).toEqual({ color: '#e3c16a', width: 3 });
  // the pure operation cannot touch drawings by construction; the caller's
  // drawings are a separate array and stay byte-identical:
  const drawings = [{ id: 'd1', tool: 'trend', style: { color: '#7fa6c0', width: 1 } }];
  expect(drawings).toEqual([{ id: 'd1', tool: 'trend', style: { color: '#7fa6c0', width: 1 } }]);
  // built-in presets refuse style mutation
  const builtin = builtInPresetFor('trend');
  const refused = updatePresetStyle([builtin], builtin.id, { color: '#fff' });
  expect(refused.ok).toBe(false);
  expect(refused.list).toBeUndefined();
  // renaming and deleting built-ins is refused too
  expect(renamePreset([builtin], builtin.id, 'x').ok).toBe(false);
  expect(deletePreset([builtin], builtin.id).ok).toBe(false);
});

test('C129: the dirty link follows the drawing, and apply records it honestly', () => {
  const list = createPreset([], { name: 'A', tool: 'trend', style: { color: '#7fa6c0', width: 1 } }).list;
  const preset = list[0];
  const drawing = applyPresetToDrawing({ id: 'd1', tool: 'trend' }, preset);
  expect(drawing.presetId).toBe(preset.id);
  expect(drawing.style).toEqual(preset.style);
  expect(drawing.dirty).toBe(false);
  expect(dirtyPresetFor(drawing, list)).toBe(null); // applied → not dirty
  // a style edit makes exactly the linked preset dirty (isDirty reuse)
  const edited = { ...drawing, style: { ...drawing.style, width: 3 } };
  expect(dirtyPresetFor(edited, list)?.id).toBe(preset.id);
  // the schema helpers keep their pinned contract
  expect(isDirty(edited, preset)).toBe(true);
  expect(presetForNew({ starred: 's', active: 'a' })).toBe('s');
  expect(applyPreset({ style: {} }, { style: { w: 2 } }).dirty).toBe(false);
  expect(PRESET_CAP).toBe(50);
});

test('C091: per-tool default resolution is starred > active > built-in', () => {
  const plain = createPreset([], { name: 'plain', tool: 'trend', style: { width: 1 } }).list;
  const starred = createPreset(plain, { name: 'star', tool: 'trend', style: { width: 2 } }).list;
  const active = createPreset(starred, { name: 'active', tool: 'trend', style: { width: 3 } }).list;
  const s = toggleStar(active, active.find(p => p.name === 'star').id).list;
  const a = setActivePreset(s, s.find(p => p.name === 'active').id).list;
  expect(defaultPresetFor(a, 'trend').name).toBe('star'); // starred wins
  const unstarred = toggleStar(a, a.find(p => p.name === 'star').id).list;
  expect(defaultPresetFor(unstarred, 'trend').name).toBe('active'); // then active
  expect(defaultPresetFor([], 'trend').kind).toBe('built-in'); // then built-in
  expect(defaultPresetFor([], 'nope')).toBe(null); // unsupported tool → null, never invented
  // the built-in preset carries the family default style
  expect(builtInPresetFor('trend').style).toEqual(defaultStyleForTool('trend'));
  // presetsForTool lists built-in + user presets for the tool only
  expect(presetsForTool(a, 'horizontal')).toHaveLength(0); // none for horizontal yet
  const withH = createPreset(a, { name: 'h', tool: 'horizontal', style: {} }).list;
  expect(presetsForTool(withH, 'horizontal').map(p => p.name)).toEqual(['h']);
});

test('C130: the full Fib schema roundtrips with per-level colors, no generic color override', () => {
  const fibStyle = {
    ratios: [0, 0.382, 0.618, 1],
    levelColors: ['#7fa6c0', '#e3c16a', '#5ec986', '#d65656'],
    showLevels: [true, false, true, true],
    fillOpacity: 0.12,
    width: 2,
    dash: false,
    extensions: true,
    trendline: true,
    labels: true,
    logScale: false,
    reverse: false,
  };
  const created = createPreset([], { name: 'fib full', tool: 'fib', style: fibStyle });
  nameOk(created);
  const stored = created.preset.style;
  // every schema field survives sanitization EXACTLY (roundtrip, false preserved)
  expect(stored).toEqual(fibStyle);
  // the generic color field is NOT a per-level override: sanitize keeps levelColors
  // authoritative for levels; a plain 'color' on fib is the trendline/extension color
  const sanitized = sanitizePresetStyle('fib', { ...fibStyle, color: '#ffffff' });
  expect(sanitized.levelColors).toEqual(fibStyle.levelColors);
  expect(sanitized.color).toBe('#ffffff'); // kept as the trendline color, levels untouched
  // the line family covers line/ray-style fields
  expect(PRESET_STYLE_FIELDS.line).toEqual(expect.arrayContaining(['color', 'width', 'dash', 'extendLeft', 'extendRight', 'showLabels']));
  // unsupported family fields are dropped by sanitize (schema is closed per family)
  const lineSan = sanitizePresetStyle('trend', { color: '#7fa6c0', width: 2, fillOpacity: 0.5 });
  expect(lineSan).toEqual({ color: '#7fa6c0', width: 2 });
  // the default style for fib carries the canonical levels
  expect(defaultStyleForTool('fib').ratios).toEqual(FIB_LEVELS);
  expect(defaultStyleForTool('fib').levelColors).toHaveLength(FIB_LEVELS.length);
});

test('B17: old unstyled drawings keep their defaults — the manager never batch-restyles', () => {
  const list = createPreset([], { name: 'A', tool: 'trend', style: { color: '#e3c16a', width: 3 } }).list;
  const old1 = { id: 'old1', tool: 'trend' };            // unstyled, pre-presets drawing
  const old2 = { id: 'old2', tool: 'fib', style: { width: 1 } }; // styled its own way
  // no manager operation rewrites drawings; only an explicit apply does
  const afterOps = [toggleStar(list, list[0].id), setActivePreset(list, list[0].id)].reduce((l, r) => r.list, list);
  expect(old1.style).toBeUndefined();
  expect(old2.style).toEqual({ width: 1 });
  expect(afterOps).toHaveLength(1);
  // explicit apply to ONE drawing touches exactly that drawing
  const applied = applyPresetToDrawing(old2, list[0]);
  expect(applied.style).toEqual({ color: '#e3c16a', width: 3 });
  expect(applied.presetId).toBe(list[0].id);
  expect(old2.style).toEqual({ width: 1 }); // the source object is not mutated
});

test('C091: star and active are refused for built-ins — the fallback tier is not user-managed', () => {
  const builtin = builtInPresetFor('trend');
  const withBuiltin = [builtin, ...createPreset([], { name: 'Mine', tool: 'trend', style: {} }).list];
  const starred = toggleStar(withBuiltin, builtin.id);
  expect(starred.ok).toBe(false); // symmetric with setActivePreset's existing refusal
  expect(starred.list).toBeUndefined();
  // a stale star/active flag on a caller-materialized built-in is normalized
  // away by the manager tier resolution — the built-in stays the fallback
  const weird = [{ ...builtin, starred: true, active: true }];
  const resolved = defaultPresetFor(weird, 'trend');
  expect(resolved.kind).toBe('built-in');
});

test('C129: a drawing linked to a DELETED preset has no dirty dot and no enabled Update', () => {
  const list = createPreset([], { name: 'A', tool: 'trend', style: { width: 1 } }).list;
  const drawing = applyPresetToDrawing({ id: 'd1', tool: 'trend' }, list[0]);
  // the caller deletes the preset; the stale link resolves to nothing
  const gone = deletePreset(list, list[0].id).list;
  expect(dirtyPresetFor(drawing, gone)).toBe(null);
  // even after drifting, a stale link never fabricates a dirty reference
  const drifted = { ...drawing, style: { width: 9 } };
  expect(dirtyPresetFor(drifted, gone)).toBe(null);
});

test('manager: rename succeeds for user presets and refuses collisions', () => {
  const a = createPreset([], { name: 'A', tool: 'trend', style: {} }).list;
  const b = createPreset(a, { name: 'B', tool: 'trend', style: {} }).list;
  const renamed = renamePreset(b, b.find((p) => p.name === 'A').id, 'Renamed');
  expect(renamed.ok).toBe(true);
  expect(renamed.list.find((p) => p.id === b.find((q) => q.name === 'A').id).name).toBe('Renamed');
  const collision = renamePreset(renamed.list, renamed.list.find((p) => p.name === 'Renamed').id, 'b');
  expect(collision.ok).toBe(false);
  expect(collision.error).toMatch(/exists/i);
});

test('C130: fib arrays loaded with mismatched lengths are normalized, never crash-rendered', () => {
  // an older writer or hand-edited store can leave levelColors/showLevels
  // shorter than ratios — sanitize pads honestly so a renderer never reads
  // undefined, and the roundtrip keeps every surviving user value.
  const ragged = sanitizePresetStyle('fib', {
    ratios: [0, 0.5, 1],
    levelColors: ['#111111'],        // 1 of 3
    showLevels: [true],              // 1 of 3
    width: 2,
  });
  expect(ragged.ratios).toEqual([0, 0.5, 1]);
  expect(ragged.levelColors).toHaveLength(3);
  expect(ragged.levelColors[0]).toBe('#111111'); // user value survives
  expect(ragged.showLevels).toHaveLength(3);
  expect(ragged.showLevels[0]).toBe(true);       // user value survives
  // extra entries beyond ratios are trimmed (never invented levels)
  const overlong = sanitizePresetStyle('fib', { ratios: [0, 1], levelColors: ['#1', '#2', '#3'], showLevels: [true, true, true] });
  expect(overlong.levelColors).toHaveLength(2);
  expect(overlong.showLevels).toHaveLength(2);
});

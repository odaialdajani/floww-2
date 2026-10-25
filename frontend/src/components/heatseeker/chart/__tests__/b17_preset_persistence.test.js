/** @jest-environment jsdom */
// B17 focused pins — preset PERSISTENCE (local device half).
// RED-first: presetPersistence.js does not exist yet.
import {
  loadPresets, savePresets, clearPresets, cloudSyncStatus, PRESET_STORAGE_VERSION,
} from '../drawings/presetPersistence';

const preset = (name, tool, style = { width: 1 }) => ({ id: 'p-' + name, name, tool, style, kind: 'user', starred: false, active: false });

beforeEach(() => { localStorage.clear(); });

test('C091/local: presets persist per scope and reload exactly, false options included', () => {
  const list = [preset('A', 'trend', { color: '#7fa6c0', width: 2, dash: false, active: false, starred: false })];
  savePresets('SPY', list);
  const back = loadPresets('SPY');
  expect(back).toEqual(list); // false flags survive the roundtrip
  // scope isolation: another ticker sees nothing
  expect(loadPresets('QQQ')).toEqual([]);
  savePresets('QQQ', [preset('Q', 'fib')]);
  expect(loadPresets('QQQ')).toHaveLength(1);
  expect(loadPresets('SPY')).toEqual(list); // untouched by the QQQ save
  clearPresets('QQQ');
  expect(loadPresets('QQQ')).toEqual([]);
  expect(loadPresets('SPY')).toEqual(list);
});

test('forward compat: an envelope from a NEWER storage version is never clobbered', () => {
  // a future build wrote version 2 — an older build must not destroy it
  localStorage.setItem('floww.drawing.presets.SPY', JSON.stringify({ v: PRESET_STORAGE_VERSION + 1, presets: [preset('future', 'trend')] }));
  // the older build reads it as empty (honest unknown), not as garbage
  expect(loadPresets('SPY')).toEqual([]);
  // and REFUSES to overwrite the newer envelope
  expect(() => savePresets('SPY', [preset('mine', 'trend')])).toThrow(/newer/i);
  // the future data is still intact for the newer build
  expect(JSON.parse(localStorage.getItem('floww.drawing.presets.SPY')).v).toBe(PRESET_STORAGE_VERSION + 1);
});

test('forward compat within v1: unknown preset fields are preserved, corrupt rows recover to empty', () => {
  // unknown extra fields on a preset roundtrip untouched (older reader, newer writer)
  const withExtra = [{ ...preset('A', 'trend'), futureField: { nested: true } }];
  savePresets('SPY', withExtra);
  expect(loadPresets('SPY')[0].futureField).toEqual({ nested: true });
  // corrupt JSON recovers to empty — never a crash, never a guessed preset
  localStorage.setItem('floww.drawing.presets.SPY', '{not json');
  expect(loadPresets('SPY')).toEqual([]);
  // non-array presets recover to empty too
  localStorage.setItem('floww.drawing.presets.SPY', JSON.stringify({ v: 1, presets: { nope: true } }));
  expect(loadPresets('SPY')).toEqual([]);
  // corrupt rows do not destroy the right to save fresh data
  savePresets('SPY', [preset('fresh', 'trend')]);
  expect(loadPresets('SPY')).toHaveLength(1);
});

test('local device half: quota, bytes and secrets refusal; no account gate anywhere', () => {
  // cap: saving more than 50 presets throws — no silent truncation
  const fifty = Array.from({ length: 51 }, (_, i) => preset('p' + i, 'trend'));
  expect(() => savePresets('SPY', fifty)).toThrow(/50|cap/i);
  expect(loadPresets('SPY')).toEqual([]); // the refused save wrote nothing
  // secrets/positions are refused — never persisted
  const leaky = [{ ...preset('A', 'trend'), apiKey: 'sk-1', positions: [1], brokerAccount: 'x' }];
  expect(() => savePresets('SPY', leaky)).toThrow(/secret/i);
  expect(localStorage.getItem('floww.drawing.presets.SPY')).toBe(null);
  // the local half is NOT blocked by account auth: persistence works with no
  // account present at all (no auth parameter exists in this module's API)
  savePresets('SPY', [preset('no-account', 'trend')]);
  expect(loadPresets('SPY')[0].name).toBe('no-account');
});

test('local device half: an oversized store is refused whole, never truncated', () => {
  // a store whose serialized form exceeds the byte cap is refused — the
  // caller surfaces the refusal instead of losing presets silently
  const huge = Array.from({ length: 20 }, (_, i) => preset('big' + i, 'fib', {
    ratios: [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1],
    levelColors: ['#7fa6c000' + i, '#e3c16a00' + i, '#5ec98600' + i, '#d6565600' + i, '#c4a1ef00' + i, '#5a9bd400' + i, '#9a9a9a00' + i],
    showLevels: [true, true, true, true, true, true, true],
    fillOpacity: 0.15, width: 2, dash: false, extensions: false, trendline: true, labels: false, logScale: false, reverse: false,
    note: 'x'.repeat(4000) + i,
  }));
  expect(() => savePresets('SPY', huge)).toThrow(/quota/i);
  expect(localStorage.getItem('floww.drawing.presets.SPY')).toBe(null);
});

test('cloud sync stays honest-external: no cloud or account claim is made locally', () => {
  const status = cloudSyncStatus();
  expect(status.available).toBe(false);
  expect(status.claim).toMatch(/local/i);
  // nothing in local storage advertises a sync state
  savePresets('SPY', [preset('A', 'trend')]);
  expect(Object.keys(localStorage).some(k => /sync|account|cloud/i.test(k))).toBe(false);
});

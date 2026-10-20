import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import ChartWorkspace from '../ChartWorkspace';
import {
  DEFAULT_SHORTCUTS, FIT_MODES, LONG_PRESS_MS, REBINDABLE_ACTIONS,
  actionFor, isTypingField, keyOf, nextFitMode, rebind, shouldHandleShortcut, watermark,
} from '../ChartShortcuts';
import { clipboardState, composeExportSvg, exportPlan } from '../ChartExport';
import { _clear } from '../persistence/layoutStore';

// Bare factory + per-test re-arm (durable pattern for this CRA setup).
jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));
const armPayload = () => {
  const axios = require('axios');
  axios.get.mockImplementation(async url => {
    const ticker = String(url).match(/price-history\/([A-Z]+)/)?.[1] ?? 'SPY';
    return { data: { ticker, query_key: '', frames: [{ time: '2026-10-06T14:00:00Z', open: 100, high: 102, low: 99, close: 101 }], candles_with_recorded_nodes: 1, node_status: 'available' } };
  });
};

beforeEach(() => { _clear(); armPayload(); window.__FLOWW_CHART_WORKSPACE__ = true; localStorage.clear(); });
afterEach(() => { window.__FLOWW_CHART_WORKSPACE__ = false; });

test('B27 typing fields never fire chart shortcuts', () => {
  expect(isTypingField({ tagName: 'INPUT' })).toBe(true);
  expect(isTypingField({ tagName: 'TEXTAREA' })).toBe(true);
  expect(isTypingField({ tagName: 'DIV', isContentEditable: true })).toBe(true);
  expect(isTypingField({ tagName: 'DIV' })).toBe(false);
  const body = { target: { tagName: 'BODY' } };
  expect(shouldHandleShortcut(body)).toBe(true);
  expect(actionFor(DEFAULT_SHORTCUTS, { target: { tagName: 'INPUT' }, key: 'a' })).toBe(null);
  expect(actionFor(DEFAULT_SHORTCUTS, { target: { tagName: 'TEXTAREA' }, key: 'r' })).toBe(null);
  expect(actionFor(DEFAULT_SHORTCUTS, body)).toBe(null); // no key
  expect(actionFor(DEFAULT_SHORTCUTS, { ...body, key: 'A' })).toBe('atlas'); // case-insensitive
  expect(actionFor(DEFAULT_SHORTCUTS, { ...body, key: 'x' })).toBe(null); // unmapped key
});

test('B27 rebind rules: typed refusals, no ambiguity, escape reserved', () => {
  expect(REBINDABLE_ACTIONS).toEqual(Object.keys(DEFAULT_SHORTCUTS));
  expect(rebind(DEFAULT_SHORTCUTS, 'atlas', 'z').atlas).toBe('z');
  expect(() => rebind(DEFAULT_SHORTCUTS, 'loop', 'z')).toThrow('unknown-action');
  expect(() => rebind(DEFAULT_SHORTCUTS, 'atlas', '')).toThrow('bad-key');
  expect(() => rebind(DEFAULT_SHORTCUTS, 'atlas', 'ab')).toThrow('bad-key');
  expect(() => rebind(DEFAULT_SHORTCUTS, 'atlas', ' ')).toThrow('bad-key');
  expect(() => rebind(DEFAULT_SHORTCUTS, 'atlas', 'escape')).toThrow('reserved-key');
  expect(() => rebind(DEFAULT_SHORTCUTS, 'atlas', 'l')).toThrow('ambiguous-key'); // l belongs to layouts
  expect(keyOf({ key: 'Escape' })).toBe('escape');
  expect(LONG_PRESS_MS).toBe(500);
});

test('B27 two auto-fit modes cycle; watermark composes source/proxy/replay', () => {
  expect(FIT_MODES).toEqual(['fit-visible', 'fit-all']);
  expect(nextFitMode('fit-visible')).toBe('fit-all');
  expect(nextFitMode('fit-all')).toBe('fit-visible');
  expect(nextFitMode('garbage')).toBe('fit-visible');
  expect(watermark({ source: 'saved-observations' })).toBe('source:saved-observations');
  expect(watermark({ source: 'saved-observations', proxy: 'local-import', replay: true })).toBe('source:saved-observations proxy:local-import replay');
  expect(watermark({})).toBe('');
});

test('B27 export plan keeps layer flags; clipboard states are explicit', () => {
  expect(exportPlan()).toEqual({ engine: { includePrimitives: true, includeCrosshair: false }, sidecar: false, clipboard: 'prompt' });
  const plan = exportPlan({ includeCrosshair: true, sidecar: true });
  expect(plan.engine.includeCrosshair).toBe(true);
  expect(plan.sidecar).toBe(true);
  expect(clipboardState(null)).toBe('copied');
  expect(clipboardState(new Error('denied'))).toBe('denied');
});

test('B27 composed SVG export: real composition, watermarks, valid XML, escaped', () => {
  const svg = composeExportSvg({
    layoutId: 'three',
    panes: [{ symbol: 'SPY<&>"X"', focused: true }, { symbol: 'QQQ', focused: false }],
    fitMode: 'fit-all',
    watermarkText: 'source:saved-observations replay',
    quality: { status: 'partial', sourceTime: '2026-10-06T14:00:00Z', coverage: '2/3 bars' },
    plan: exportPlan({ includeCrosshair: true }),
  });
  expect(svg).toContain('three composition');
  expect(svg).toContain('fit fit-all');
  expect(svg).toContain('source:saved-observations replay');
  expect(svg).toContain('quality partial');
  expect(svg).toContain('crosshair:on');
  // XML escaping round-trips through a real parser: the hostile symbol text
  // re-emerges exactly and the document carries no parser error.
  const parsed = new DOMParser().parseFromString(svg, 'image/svg+xml');
  expect(parsed.querySelector('parsererror')).toBe(null);
  const texts = Array.from(parsed.querySelectorAll('text')).map(t => t.textContent);
  expect(texts.some(t => t.includes('SPY<&>"X" (focused)'))).toBe(true);
  expect(parsed.querySelectorAll('rect').length).toBeGreaterThanOrEqual(3); // bg + 2 panes
});

test('B27 mounted keyboard map: actions fire, typing never does, escape closes', async () => {
  render(<ChartWorkspace ticker="SPY" open useNew />);
  // Replay is rendered ABOVE the chips row (DOM order) with a touch-sized control.
  const pane = screen.getByTestId('replay-touch').closest('[data-testid]');
  expect(pane).toBeTruthy();
  const replayTop = await act(async () => {
    const order = screen.getByTestId('replay-touch').compareDocumentPosition(screen.getByRole('group', { name: 'Chart pane layout' }));
    return order & Node.DOCUMENT_POSITION_FOLLOWING; // replay comes first
  });
  expect(replayTop).not.toBe(0);
  // 'r' toggles replay with a visible banner + watermark gains replay.
  await act(async () => { fireEvent.keyDown(window, { key: 'r' }); });
  expect(screen.getByTestId('replay-banner')).toBeInTheDocument();
  expect(screen.getByTestId('chart-watermark').textContent).toContain('replay');
  // Escape closes the replay state first.
  await act(async () => { fireEvent.keyDown(window, { key: 'Escape' }); });
  expect(screen.queryByTestId('replay-banner')).toBe(null);
  // 'a' toggles Atlas; 'f' cycles auto-fit with a visible label.
  await act(async () => { fireEvent.keyDown(window, { key: 'a' }); });
  expect(screen.getByTestId('atlas-toggle')).toHaveAttribute('aria-pressed', 'true');
  await act(async () => { fireEvent.keyDown(window, { key: 'f' }); });
  expect(screen.getByTestId('fit-mode').textContent).toContain('fit-all');
  // 'l' opens the layouts sheet; Escape closes the topmost overlay FIRST
  // (the sheet, even with Atlas open), then Atlas on the next press.
  await act(async () => { fireEvent.keyDown(window, { key: 'l' }); });
  expect(screen.getByTestId('layouts-panel')).toHaveAttribute('open', '');
  await act(async () => { fireEvent.keyDown(window, { key: 'Escape' }); });
  expect(screen.getByTestId('layouts-panel')).not.toHaveAttribute('open');
  expect(screen.getByTestId('atlas-toggle')).toHaveAttribute('aria-pressed', 'true'); // still open
  await act(async () => { fireEvent.keyDown(window, { key: 'Escape' }); });
  expect(screen.getByTestId('atlas-toggle')).toHaveAttribute('aria-pressed', 'false');
  // Typing field: keydown targeted at the import input never fires shortcuts.
  await act(async () => { fireEvent.keyDown(window, { key: 'a' }); });
  expect(screen.getByTestId('atlas-toggle')).toHaveAttribute('aria-pressed', 'true');
  const input = screen.getByTestId('layout-import');
  await act(async () => { fireEvent.keyDown(input, { key: 'a' }); });
  // The 'a' inside the typing field did NOT re-toggle Atlas.
  expect(screen.getByTestId('atlas-toggle')).toHaveAttribute('aria-pressed', 'true');
});

test('B27 mounted rebind: capture, visible success and typed refusal', async () => {
  render(<ChartWorkspace ticker="SPY" open useNew />);
  await act(async () => { fireEvent.keyDown(window, { key: 'l' }); });
  const rebindAtlas = screen.getByTestId('rebind-atlas');
  await act(async () => { rebindAtlas.click(); });
  expect(rebindAtlas).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByTestId('layout-status').textContent).toContain('Press a new key for atlas');
  await act(async () => { fireEvent.keyDown(window, { key: 'z' }); });
  expect(screen.getByTestId('key-atlas').textContent).toBe('z');
  expect(screen.getByTestId('layout-status').textContent).toContain('Rebound atlas to z');
  // The new binding fires live.
  await act(async () => { fireEvent.keyDown(window, { key: 'z' }); });
  expect(screen.getByTestId('atlas-toggle')).toHaveAttribute('aria-pressed', 'true');
  // Ambiguous rebind is refused visibly.
  await act(async () => { screen.getByTestId('rebind-atlas').click(); });
  await act(async () => { fireEvent.keyDown(window, { key: 'l' }); }); // layouts owns l
  expect(screen.getByTestId('layout-status').textContent).toContain('Rebind refused: ambiguous-key');
  expect(screen.getByTestId('key-atlas').textContent).toBe('z'); // unchanged
});

test('B27 mounted long-press: touch hold opens the sheet, short tap does not', async () => {
  jest.useFakeTimers();
  try {
    render(<ChartWorkspace ticker="SPY" open useNew />);
    const layout = screen.getByTestId('pane-layout');
    await act(async () => { fireEvent.pointerDown(layout, { pointerType: 'mouse' }); });
    jest.advanceTimersByTime(600);
    expect(screen.getByTestId('layouts-panel')).not.toHaveAttribute('open'); // mouse never long-presses
    await act(async () => { fireEvent.pointerDown(layout, { pointerType: 'touch' }); });
    await act(async () => { jest.advanceTimersByTime(500); });
    expect(screen.getByTestId('layouts-panel')).toHaveAttribute('open', '');
    expect(screen.getByTestId('layout-status').textContent).toContain('Long-press: layouts opened.');
    // A short tap cancels: hold briefly, release, advance — sheet stays closed.
    await act(async () => { fireEvent.keyDown(window, { key: 'Escape' }); });
    await act(async () => { fireEvent.pointerDown(layout, { pointerType: 'touch' }); });
    await act(async () => { fireEvent.pointerUp(layout); });
    await act(async () => { jest.advanceTimersByTime(600); });
    expect(screen.getByTestId('layouts-panel')).not.toHaveAttribute('open');
  } finally { jest.useRealTimers(); }
});

test('B27 mounted export image: composed SVG copied; denial is a visible state', async () => {
  const writeText = jest.fn(async () => {});
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
  render(<ChartWorkspace ticker="SPY" open useNew />);
  await act(async () => { screen.getByTestId('layout-three').click(); });
  await act(async () => { screen.getByTestId('export-image').click(); });
  await waitFor(() => expect(screen.getByTestId('export-status')).toBeInTheDocument());
  expect(screen.getByTestId('export-status').textContent).toBe('Export image copied.');
  const svg = writeText.mock.calls[0][0];
  expect(svg).toContain('three composition');
  expect(svg).toContain('SPY');
  expect(svg).toContain('source:saved-observations');
  expect(new DOMParser().parseFromString(svg, 'image/svg+xml').querySelector('parsererror')).toBe(null);
  // Clipboard refusal is explicit and visible — never a silent failure.
  Object.defineProperty(navigator, 'clipboard', { value: { writeText: jest.fn(async () => { throw new Error('NotAllowedError'); }) }, configurable: true });
  await act(async () => { screen.getByTestId('export-image').click(); });
  await waitFor(() => expect(screen.getByTestId('export-status').textContent).toContain('Export denied'));
});

test('B27 fit mode persists with the composition; bottom-sheet CSS is real', async () => {
  const fs = require('fs');
  const path = require('path');
  const css = fs.readFileSync(path.join(__dirname, '..', 'ChartWorkspace.css'), 'utf8');
  // Touch replay is raised above the chips; the phone sheet is keyboard-clear.
  expect(css).toMatch(/\.touch-replay \{[^}]*z-index: 3/);
  expect(css).toMatch(/max-height: 60dvh/);
  expect(css).toMatch(/env\(safe-area-inset-bottom\)/);
  const { act: act2 } = require('@testing-library/react');
  const first = render(<ChartWorkspace ticker="SPY" open useNew />);
  await act2(async () => { fireEvent.keyDown(window, { key: 'f' }); });
  await act2(async () => { await new Promise(r => setTimeout(r, 400)); }); // autosave debounce
  const stored = JSON.parse(localStorage.getItem('floww.chart.layout.workspace-current'));
  expect(stored.fitMode).toBe('fit-all');
  first.unmount();
  render(<ChartWorkspace ticker="SPY" open useNew />);
  await act2(async () => { await new Promise(r => setTimeout(r, 100)); });
  expect(screen.getByTestId('fit-mode').textContent).toContain('fit-all'); // restored on reopen
});

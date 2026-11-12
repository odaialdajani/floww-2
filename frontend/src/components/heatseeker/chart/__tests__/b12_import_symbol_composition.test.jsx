/** @jest-environment jsdom */
// R02 / B12: a supplied symbols array must FULLY determine the composition.
//
// The reducer's 'symbols' action mapped panes by index and left any pane
// beyond the supplied array UNCHANGED, so its PREVIOUS symbol survived. An
// import of a 2-symbol file into a 5-pane arrangement therefore rendered
// ['SPY','QQQ','IWM','DIA','TLT'] — three stale symbols the imported file
// never contained — while the status note said "Layout imported.". The mixed
// composition was autosaved, so it survived reload.
//
// Contract: the symbols array is the durable composition identity. It must
// determine every pane it addresses, and a short array must not silently
// blend in the previous layout's symbols.
import React from 'react';
import { act, fireEvent, render } from '@testing-library/react';
import ChartWorkspaceModule from '../ChartWorkspace';
import { createLayout, migrate, sanitizeImport } from '../persistence/layoutSchema';
import { _clear } from '../persistence/layoutStore';

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));
const frames = [
  { time: '2026-10-06T14:00:00Z', open: 100, high: 102, low: 99, close: 101, volume: 100 },
  { time: '2026-10-06T14:30:00Z', open: 101, high: 103, low: 100, close: 102, volume: 200 },
];
beforeEach(() => {
  _clear(); localStorage.clear();
  require('axios').get.mockReset();
  require('axios').get.mockImplementation(async (url, config) => {
    const ticker = String(url).match(/price-history\/([A-Z]+)/)?.[1] || 'SPY';
    const scope = config?.params?.query_key || ticker + ':scope';
    return { data: { ticker, query_key: scope, scopes: [scope], frames,
      candles_with_recorded_nodes: 0, node_status: 'available' } };
  });
});
afterEach(() => { _clear(); localStorage.clear(); });

const slots = () => [...document.querySelectorAll('.pane-slot')];
const symbols = () => slots().map(slot => slot.querySelector('.price-chart-symbol')?.textContent);
const settle = async (ms = 250) => { await act(async () => { await new Promise(r => setTimeout(r, ms)); }); };
// The autosave is debounced (300ms in layoutStore.scheduleAutosave).
const settleAutosave = async () => { await act(async () => { await new Promise(r => setTimeout(r, 500)); }); };

const importInto = async (payload) => {
  const input = document.querySelector('[data-testid="layout-import"]');
  const file = new File([JSON.stringify(payload)], 'layout.json', { type: 'application/json' });
  await act(async () => {
    fireEvent.change(input, { target: { files: [file] } });
    await new Promise(r => setTimeout(r, 250));
  });
};

test('a short symbols array leaves no stale symbol on the panes it does not address', async () => {
  const view = render(<ChartWorkspaceModule ticker="SPY" open useNew />);
  await settle();
  // A five-pane composition whose panes carry five DISTINCT symbols. This is
  // the exact live reproduction: import the five-symbol layout first, so the
  // workspace really holds ['SPY','QQQ','IWM','DIA','TLT'].
  await importInto({ layoutId: 'five-stack', symbols: ['SPY', 'QQQ', 'IWM', 'DIA', 'TLT'], focusedIndex: 4 });
  expect(symbols()).toEqual(['SPY', 'QQQ', 'IWM', 'DIA', 'TLT']);

  // Now import a SHORT symbols array into the same five-pane arrangement.
  await importInto({ layoutId: 'five-stack', symbols: ['SPY', 'QQQ'], focusedIndex: 4 });
  const after = symbols();
  // Every symbol now shown must come from the imported file — the three
  // surplus panes must not keep the stale IWM/DIA/TLT.
  expect(after).not.toContain('IWM');
  expect(after).not.toContain('DIA');
  expect(after).not.toContain('TLT');
  expect(after.slice(0, 2)).toEqual(['SPY', 'QQQ']);
  view.unmount();
});

test('a short import does not silently persist a mixed composition', async () => {
  const view = render(<ChartWorkspaceModule ticker="SPY" open useNew />);
  await settle();
  await importInto({ layoutId: 'five-stack', symbols: ['SPY', 'QQQ', 'IWM', 'DIA', 'TLT'], focusedIndex: 4 });
  expect(symbols()).toEqual(['SPY', 'QQQ', 'IWM', 'DIA', 'TLT']);
  await importInto({ layoutId: 'five-stack', symbols: ['SPY', 'QQQ'], focusedIndex: 4 });
  await settleAutosave();
  const raw = localStorage.getItem('floww.chart.layout.workspace-current');
  expect(raw).not.toBeNull();
  const persistedSymbols = JSON.parse(raw).symbols || [];
  // Whatever the fix does (clear the surplus panes or refuse the import), the
  // persisted composition must not be a blend of the imported array and the
  // previous layout's symbols.
  expect(persistedSymbols).not.toContain('IWM');
  expect(persistedSymbols).not.toContain('DIA');
  expect(persistedSymbols).not.toContain('TLT');
  view.unmount();
});

test('a FULL-LENGTH symbols array still restores exactly, unchanged', async () => {
  const view = render(<ChartWorkspaceModule ticker="SPY" open useNew />);
  await settle();
  await importInto({ layoutId: 'three', symbols: ['IWM', 'DIA', 'TLT'], focusedIndex: 1 });
  expect(symbols()).toEqual(['IWM', 'DIA', 'TLT']);
  await settleAutosave();
  const raw = localStorage.getItem('floww.chart.layout.workspace-current');
  expect(JSON.parse(raw).symbols).toEqual(['IWM', 'DIA', 'TLT']);
  view.unmount();
});

test('the sanitized import path carries the symbols array through unchanged', () => {
  // The schema layer must not silently truncate or pad the array.
  const clean = sanitizeImport({ layoutId: 'five-stack', symbols: ['SPY', 'QQQ'], focusedIndex: 4 });
  const { layout } = migrate(clean);
  expect(layout.symbols).toEqual(['SPY', 'QQQ']);
  expect(createLayout({ symbols: ['SPY', 'QQQ'] }).symbols).toEqual(['SPY', 'QQQ']);
});

/** @jest-environment jsdom */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import SkylitHeatmapGrid from './SkylitHeatmapGrid';

const STRIKES = [660, 658, 656, 654, 652, 650, 648, 646, 644, 642];
const EXPS = ['2026-09-18', '2026-09-25'];

function mockData() {
  const grid = {};
  for (const e of EXPS) {
    grid[e] = {};
    for (const s of STRIKES) grid[e][String(s)] = (s - 650) * 1000;
  }
  return { asof: '2026-09-03T00:00:00Z', grid: { expiries: EXPS, strikes: STRIKES, grid } };
}

test('renders every strike row by default', () => {
  const { container } = render(<SkylitHeatmapGrid data={mockData()} spot={650} ticker="SPY" />);
  expect(container.querySelectorAll('tbody tr.trin-row').length).toBe(10);
  expect(screen.queryByTestId('skylit-grid-window-note')).not.toBeInTheDocument();
});

test('windowRows slices around spot with a count note', () => {
  const { container } = render(
    <SkylitHeatmapGrid data={mockData()} spot={650} ticker="SPY" windowRows={5} />
  );
  const rows = container.querySelectorAll('tbody tr.trin-row');
  expect(rows.length).toBe(5);
  // Centered on spot 650: 654, 652, 650, 648, 646 (descending).
  expect(rows[2].textContent).toContain('650');
  const note = screen.getByTestId('skylit-grid-window-note');
  expect(note.textContent).toContain('5 of 10');
});

test('density="full" enlarges the table', () => {
  const { container } = render(
    <SkylitHeatmapGrid data={mockData()} spot={650} ticker="SPY" density="full" />
  );
  expect(container.querySelector('table.trin-grid-table').className).toContain('density-full');
  expect(container.querySelectorAll('tbody tr.trin-row').length).toBe(10);
});

test('strike rail shows concentration bars from aggregated rows', () => {
  const d = mockData();
  d.strikes = STRIKES.map((s) => ({ strike: s, gex: (s - 650) * 1000, call_gex: (s - 650) * 500, put_gex: (s - 650) * 500 }));
  const { container } = render(<SkylitHeatmapGrid data={d} spot={650} ticker="SPY" />);
  expect(container.querySelectorAll('[data-testid="skylit-conc-bar"]').length).toBeGreaterThan(0);
});

test('expiry headers carry coverage titles and 0DTE contribution shows', () => {
  const today = new Date();
  // Local-calendar date: the grid compares local midnights (new Date(y, m, d)),
  // so build the fixture the same way — toISOString() is UTC and drifts a day
  // ahead of local time in western timezones after 20:00 ET.
  const pad = (n) => String(n).padStart(2, '0');
  const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const e0 = iso(today);
  const e1 = iso(new Date(today.getTime() + 86400000 * 7));
  const grid = { [e0]: { 650: 1000 }, [e1]: { 650: 3000 } };
  const d = { asof: new Date().toISOString(), grid: { expiries: [e0, e1], strikes: [650], grid } };
  const { container } = render(<SkylitHeatmapGrid data={d} spot={650} ticker="SPY" />);
  const ths = container.querySelectorAll('th.trin-th-exp');
  expect(ths[0].title).toContain('0DTE');
  expect(ths[1].title).toContain('7d left');
  expect(screen.getByTestId('skylit-grid-0dte').textContent).toContain('25.0%');
});

test('cell click reports strike, expiry, value', () => {
  const onCellClick = jest.fn();
  const { container } = render(
    <SkylitHeatmapGrid data={mockData()} spot={650} ticker="SPY" onCellClick={onCellClick} />
  );
  const cell = container.querySelector('tbody tr.trin-row td.trin-cell');
  fireEvent.click(cell);
  expect(onCellClick).toHaveBeenCalledTimes(1);
  const [strike, expiry, value] = onCellClick.mock.calls[0];
  expect(typeof strike).toBe('number');
  expect(EXPS).toContain(expiry);
  expect(typeof value).toBe('number');
});

test('keyboard Enter/Space on a cell selects it; empty cells ignore keys', () => {
  const onCellClick = jest.fn();
  const { container } = render(
    <SkylitHeatmapGrid data={mockData()} spot={650} ticker="SPY" onCellClick={onCellClick} />
  );
  const cell = container.querySelector('tbody tr.trin-row td.trin-cell');
  expect(cell.getAttribute('tabIndex')).toBe('0');
  expect(cell.getAttribute('role')).toBe('gridcell');
  fireEvent.keyDown(cell, { key: 'Enter' });
  fireEvent.keyDown(cell, { key: ' ' });
  expect(onCellClick).toHaveBeenCalledTimes(2);
  // Unequal strike/expiry grid: an empty (no-data) cell is untabbable and
  // keyboard-inert — focus never lands on missing data.
  const sparse = { asof: '2026-09-03T00:00:00Z',
    grid: { expiries: EXPS, strikes: [660, 650], grid: { [EXPS[0]]: { 650: 5 } } } };
  const { container: c2 } = render(
    <SkylitHeatmapGrid data={sparse} spot={650} ticker="SPY" onCellClick={onCellClick} />
  );
  const cells = c2.querySelectorAll('tbody tr.trin-row td.trin-cell');
  expect(cells.length).toBeGreaterThan(0);
  const inert = Array.from(cells).filter((td) => td.getAttribute('tabIndex') === '-1');
  expect(inert.length).toBeGreaterThan(0);
  const before = onCellClick.mock.calls.length;
  inert.forEach((td) => fireEvent.keyDown(td, { key: 'Enter' }));
  expect(onCellClick.mock.calls.length).toBe(before);
});

test('R6-1: empty→populated→unavailable never changes hook order', () => {
  const empty = { asof: '2026-09-03T00:00:00Z', grid: { expiries: [], strikes: [], grid: {} } };
  const { container, rerender } = render(
    <SkylitHeatmapGrid data={empty} spot={650} ticker="SPY" />
  );
  expect(container.querySelector('.skylit-heatmap-empty')).not.toBeNull();
  const full = mockData();
  expect(() => {
    rerender(<SkylitHeatmapGrid data={full} spot={650} ticker="SPY" />);
  }).not.toThrow();
  expect(container.querySelectorAll('tbody tr.trin-row').length).toBe(10);
  expect(() => {
    rerender(
      <SkylitHeatmapGrid data={full} spot={650} ticker="SPY" metric="delta" />
    );
  }).not.toThrow();
  // Missing delta surface: unavailable block, never raw values.
  expect(screen.getByTestId('skylit-metric-unavailable')).toBeInTheDocument();
  expect(screen.queryByText('660')).toBeNull();
});

test('R6-1: present delta overlay renders its own cells, not raw', () => {
  const d = mockData();
  d.metrics = {
    grids: {
      delta: {
        grid: { [EXPS[0]]: { 650: 777 }, [EXPS[1]]: { 650: 888 } },
        exposure_basis: 'OI_DELTA_WEIGHTED',
      },
    },
  };
  const { container } = render(
    <SkylitHeatmapGrid data={d} spot={650} ticker="SPY" metric="delta" />
  );
  expect(screen.queryByTestId('skylit-metric-unavailable')).toBeNull();
  expect(container.textContent).toContain('$0.8K');
  expect(screen.getByTestId('skylit-grid-basis').textContent).toContain('OI_DELTA_WEIGHTED');
});

test('R7-02: vex view without a surface is explicitly unavailable, not blank', () => {
  const d = mockData();
  const { container } = render(
    <SkylitHeatmapGrid data={d} spot={650} ticker="SPY" viewMode="vex" />
  );
  expect(screen.getByTestId('skylit-surface-unavailable')).toBeInTheDocument();
  expect(screen.getByTestId('skylit-surface-unavailable').textContent).toContain('VEX unavailable');
  // No silent zero cells.
  expect(container.querySelectorAll('td.trin-cell').length).toBe(0);
});

test('R7-02: vex view with a surface renders its cells', () => {
  const d = mockData();
  d.grid.vex_grid = { [EXPS[0]]: { 650: 2500 }, [EXPS[1]]: { 650: -1200 } };
  d.grid.vex_meta = { exposure_basis: 'VEX_1VOLPT', model: 'local-bs-vanna.v1', status: 'ok', reason: null };
  const { container } = render(
    <SkylitHeatmapGrid data={d} spot={650} ticker="SPY" viewMode="vex" />
  );
  expect(screen.queryByTestId('skylit-surface-unavailable')).toBeNull();
  expect(container.querySelectorAll('td.trin-cell').length).toBeGreaterThan(0);
});

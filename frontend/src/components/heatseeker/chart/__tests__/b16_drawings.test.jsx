import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { TOOLS, createDrawing, magnet, reduceDrawings } from '../drawings/drawingReducer';
import DrawingRail from '../drawings/DrawingRail';
import { FIB_LEVELS, fibPrices, riskBox } from '../drawings/advancedTools';
import { PRESET_CAP, presetForNew, isDirty, applyPreset } from '../drawings/presetSchema';
test('drawings + presets', () => {
  expect(TOOLS).toContain('trend');
  expect(() => createDrawing('nope', [])).toThrow('unsupported-tool');
  const d = createDrawing('trend', [{ t: 1, p: 100 }]);
  expect(reduceDrawings([], { type: 'add', drawing: d })).toHaveLength(1);
  expect(reduceDrawings([d], { type: 'hide', id: d.id })[0].visible).toBe(false);
  expect(magnet(100.2, { open: 100, high: 101, low: 99, close: 100.5 })).toBe(100);
  expect(FIB_LEVELS).toContain(0.618);
  expect(fibPrices(100, 90)[0].price).toBe(100);
  expect(riskBox(100, 95, 110).analysisOnly).toBe(true);
  expect(PRESET_CAP).toBe(50);
  expect(presetForNew({ starred: 's', active: 'a' })).toBe('s');
  expect(isDirty({ style: { w: 1 } }, { style: { w: 2 } })).toBe(true);
  expect(applyPreset({ style: {} }, { style: { w: 2 } }).dirty).toBe(false);
});
test('rail lists drawings with select/delete/lock/hide actions', () => {
  const drawings = [
    { id: 'd1', tool: 'trend', visible: true, locked: false },
    { id: 'd2', tool: 'horizontal', visible: false, locked: true },
  ];
  const calls = {};
  const on = (name) => (id) => { calls[name] = id; };
  render(<DrawingRail drawings={drawings} selectedId="d1" onSelect={on('select')}
    onDelete={on('delete')} onToggleLock={on('lock')} onToggleHide={on('hide')} />);
  expect(screen.getByTestId('drawing-rail')).toBeInTheDocument();
  expect(screen.getAllByTestId('rail-drawing')).toHaveLength(2);
  fireEvent.click(screen.getByTestId('rail-select-d2'));
  expect(calls.select).toBe('d2');
  fireEvent.click(screen.getByTestId('rail-delete-d1'));
  expect(calls.delete).toBe('d1');
  fireEvent.click(screen.getByTestId('rail-lock-d1'));
  expect(calls.lock).toBe('d1');
  fireEvent.click(screen.getByTestId('rail-hide-d1'));
  expect(calls.hide).toBe('d1');
});
test('alert lines render armed levels and refuse stale ones on the chart', () => {
  const { default: RecordedPriceChart } = require('../../RecordedPriceChart');
  const frames = [
    { time: '2026-10-06T13:30:00+00:00', open: 100, high: 102, low: 99, close: 101, duration_seconds: 60, nodes: [] },
    { time: '2026-10-06T13:31:00+00:00', open: 101, high: 103, low: 100, close: 102, duration_seconds: 60, nodes: [] },
  ];
  const { unmount } = render(<RecordedPriceChart ticker="SPY" frames={frames}
    alertLines={[{ id: 'a1', price: 101, state: 'armed' }, { id: 'a2', price: 100.5, state: 'stale' }]} />);
  const lines = screen.getAllByTestId('alert-line');
  expect(lines).toHaveLength(2);
  expect(lines[0].getAttribute('data-state')).toBe('armed');
  expect(lines[1].getAttribute('data-state')).toBe('stale');
  expect(screen.getByRole('note')).toHaveTextContent(/stale alert refused/i);
  unmount();
});

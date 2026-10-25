/** @jest-environment jsdom */
// The INDICATOR BROWSER PANEL — the visible, searchable, grouped catalog
// with active-instance settings (B17/C045/C046/C050/C116/C131-class UI).
// RED-first: IndicatorsPanel.jsx does not exist yet.
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import IndicatorsPanel from '../indicators/IndicatorsPanel';
import { createStudyInstance } from '../indicators/registry';

const FRAMES = [
  { time: '2026-10-19T13:30:00.000Z', close: 100, volume: 10, high: 101, low: 99, open: 100 },
  { time: '2026-10-19T14:30:00.000Z', close: 102, volume: 10, high: 103, low: 101, open: 101 },
  { time: '2026-10-26T13:30:00.000Z', close: 130, volume: 10, high: 131, low: 129, open: 130 },
];
const baseProps = { frames: FRAMES };

test('the panel mounts a searchable grouped catalog with active counts', () => {
  render(<IndicatorsPanel {...baseProps} instances={[]} />);
  expect(screen.getByTestId('indicators-panel')).toBeInTheDocument();
  expect(screen.getByTestId('indicators-search')).toBeInTheDocument();
  expect(screen.getByTestId('indicators-group-price')).toBeInTheDocument();
  expect(screen.getByTestId('indicators-group-panes')).toBeInTheDocument();
  expect(screen.getByTestId('indicators-group-context')).toBeInTheDocument();
  expect(screen.getByTestId('catalog-row-sma')).toBeInTheDocument();
  expect(screen.getByTestId('catalog-row-ema')).toBeInTheDocument();
  expect(screen.getByTestId('catalog-row-bollinger')).toBeInTheDocument();
  expect(screen.getByTestId('catalog-row-vwap')).toBeInTheDocument();
  // search filters the catalog
  fireEvent.change(screen.getByTestId('indicators-search'), { target: { value: 'ema' } });
  expect(screen.queryByTestId('catalog-row-sma')).not.toBeInTheDocument();
  expect(screen.getByTestId('catalog-row-ema')).toBeInTheDocument();
});

test('Add uses named useful defaults; the EMA 9 preset chip sends period 9', () => {
  const onCreate = jest.fn();
  render(<IndicatorsPanel {...baseProps} instances={[]} onCreate={onCreate} />);
  fireEvent.click(screen.getByTestId('catalog-add-ema'));
  expect(onCreate).toHaveBeenCalledWith('ema', { period: 20 });
  fireEvent.click(screen.getByTestId('catalog-preset-EMA 9'));
  expect(onCreate).toHaveBeenCalledWith('ema', { period: 9 });
  fireEvent.click(screen.getByTestId('catalog-add-vwap'));
  expect(onCreate).toHaveBeenCalledWith('vwap', { source: 'hlc3', bandBasis: 'std', multipliers: [1, 2, 3], bands: false, anchor: 'session' });
});

test('Volume is the REAL pane toggle — it never calls onCreate, and reflects pane state', () => {
  const onTogglePane = jest.fn();
  const onCreate = jest.fn();
  render(<IndicatorsPanel {...baseProps} instances={[]} onCreate={onCreate}
    onTogglePane={onTogglePane} paneState={{ 'volume-pane': true }} />);
  const vol = screen.getByTestId('pane-toggle-volume-pane');
  expect(vol.getAttribute('aria-pressed')).toBe('true');
  expect(screen.queryByTestId('catalog-add-volume')).not.toBeInTheDocument(); // NO fake Add
  fireEvent.click(vol);
  expect(onTogglePane).toHaveBeenCalledWith('volume-pane');
  expect(onCreate).not.toHaveBeenCalled();
});

test('availability-controlled panes: CVD/profile toggle only when the data exists; the reason shows BEFORE clicking', () => {
  const onTogglePane = jest.fn();
  const { rerender } = render(<IndicatorsPanel {...baseProps} instances={[]} onTogglePane={onTogglePane}
    availability={{ cvd: false, profile: true }} paneState={{ cvd: false, profile: true }} />);
  // CVD unavailable -> honest reason row, no working toggle
  expect(screen.getByTestId('pane-unavailable-cvd')).toHaveTextContent(/source/i);
  expect(screen.queryByTestId('pane-toggle-cvd')).not.toBeInTheDocument();
  // profile available -> a real toggle reflecting state
  const prof = screen.getByTestId('pane-toggle-profile');
  expect(prof.getAttribute('aria-pressed')).toBe('true');
  fireEvent.click(prof);
  expect(onTogglePane).toHaveBeenCalledWith('profile');
  rerender(<IndicatorsPanel {...baseProps} instances={[]} onTogglePane={onTogglePane}
    availability={{ cvd: true, profile: true }} paneState={{ cvd: false, profile: true }} />);
  expect(screen.getByTestId('pane-toggle-cvd')).toBeInTheDocument(); // available now
});

test('exposure-vwap stays an honest WHY-unavailable context row — never a fake Add', () => {
  render(<IndicatorsPanel {...baseProps} instances={[]} />);
  const row = screen.getByTestId('catalog-row-exposure-vwap');
  expect(row).toHaveTextContent(/board source/i);
  expect(screen.queryByTestId('catalog-add-exposure-vwap')).not.toBeInTheDocument();
});

test('active-instance settings editors drive real settings updates (period, multiple, anchor, source, bands, basis)', () => {
  const onUpdateSettings = jest.fn();
  const vwap = createStudyInstance('vwap', { source: 'hlc3', bandBasis: 'std', multipliers: [1, 2, 3], bands: false, anchor: 'week' });
  const ema = createStudyInstance('ema', { period: 20 });
  render(<IndicatorsPanel {...baseProps} instances={[ema, vwap]} onUpdateSettings={onUpdateSettings} />);
  // EMA period
  fireEvent.change(screen.getByTestId('instance-period-' + ema.instanceId), { target: { value: '50' } });
  expect(onUpdateSettings).toHaveBeenCalledWith(ema.instanceId, { period: 50 });
  // VWAP source
  fireEvent.change(screen.getByTestId('instance-source-' + vwap.instanceId), { target: { value: 'close' } });
  expect(onUpdateSettings).toHaveBeenCalledWith(vwap.instanceId, expect.objectContaining({ source: 'close' }));
  // VWAP anchor (the C050 control)
  fireEvent.change(screen.getByTestId('instance-anchor-' + vwap.instanceId), { target: { value: 'month' } });
  expect(onUpdateSettings).toHaveBeenCalledWith(vwap.instanceId, expect.objectContaining({ anchor: 'month' }));
  // bands on
  fireEvent.click(screen.getByTestId('instance-bands-' + vwap.instanceId));
  expect(onUpdateSettings).toHaveBeenCalledWith(vwap.instanceId, expect.objectContaining({ bands: true }));
});

test('multipliers edit within bounds: add up to 3, remove one, out-of-bounds refused', () => {
  const onUpdateSettings = jest.fn();
  const vwap = createStudyInstance('vwap', { source: 'hlc3', bandBasis: 'std', multipliers: [1, 2], bands: false, anchor: 'session' });
  const { rerender } = render(<IndicatorsPanel {...baseProps} instances={[vwap]} onUpdateSettings={onUpdateSettings} />);
  const input = screen.getByTestId('instance-multiplier-input-' + vwap.instanceId);
  fireEvent.change(input, { target: { value: '3' } });
  fireEvent.click(screen.getByTestId('instance-multiplier-add-' + vwap.instanceId));
  expect(onUpdateSettings).toHaveBeenLastCalledWith(vwap.instanceId, expect.objectContaining({ multipliers: [1, 2, 3] }));
  // an OUT-OF-BOUNDS multiplier (7 > 5) is refused — no update is sent
  fireEvent.change(input, { target: { value: '7' } });
  fireEvent.click(screen.getByTestId('instance-multiplier-add-' + vwap.instanceId));
  expect(onUpdateSettings).toHaveBeenCalledTimes(1);
  // the caller APPLIES the update and re-renders with the new settings
  const withThree = { ...vwap, settings: { ...vwap.settings, multipliers: [1, 2, 3] } };
  rerender(<IndicatorsPanel {...baseProps} instances={[withThree]} onUpdateSettings={onUpdateSettings} />);
  // a FULL set (3 pairs, C116) offers no add input at all — the honest bound
  expect(screen.queryByTestId('instance-multiplier-input-' + vwap.instanceId)).not.toBeInTheDocument();
  expect(screen.getByTestId('instance-multiplier-note-' + vwap.instanceId).textContent).toMatch(/3/);
  // removing one reports the filtered list from the CURRENT settings
  fireEvent.click(screen.getByTestId('instance-multiplier-remove-' + vwap.instanceId + '-2'));
  expect(onUpdateSettings).toHaveBeenLastCalledWith(vwap.instanceId, expect.objectContaining({ multipliers: [1, 3] }));
});

test('coverage label: a week-anchored instance over a two-week window shows the honest partial state', () => {
  const vwap = createStudyInstance('vwap', { source: 'hlc3', bandBasis: 'std', multipliers: [1], bands: false, anchor: 'week' });
  render(<IndicatorsPanel {...baseProps} instances={[vwap]} />);
  const cov = screen.getByTestId('instance-coverage-' + vwap.instanceId);
  expect(cov.textContent).toMatch(/week|2026-W/i);       // names the anchor/period facts
  expect(cov.textContent).toMatch(/partial|full/i);        // the measured state, never silent
});

test('the builtin-VWAP reconciliation note appears only when both the builtin overlay and an instance are on', () => {
  const vwap = createStudyInstance('vwap', { source: 'hlc3', bandBasis: 'std', multipliers: [1], bands: false, anchor: 'session' });
  const { rerender } = render(<IndicatorsPanel {...baseProps} instances={[vwap]} builtinVwapOn={false} />);
  expect(screen.queryByTestId('builtin-vwap-note')).not.toBeInTheDocument();
  rerender(<IndicatorsPanel {...baseProps} instances={[vwap]} builtinVwapOn={true} />);
  expect(screen.getByTestId('builtin-vwap-note')).toHaveTextContent(/default VWAP/i);
});

test('visibility and remove report through their callbacks', () => {
  const onToggleVisible = jest.fn();
  const onRemove = jest.fn();
  const ema = createStudyInstance('ema', { period: 9 });
  render(<IndicatorsPanel {...baseProps} instances={[ema]} onToggleVisible={onToggleVisible} onRemove={onRemove} />);
  fireEvent.click(screen.getByTestId('instance-visible-' + ema.instanceId));
  expect(onToggleVisible).toHaveBeenCalledWith(ema.instanceId);
  fireEvent.click(screen.getByTestId('instance-remove-' + ema.instanceId));
  expect(onRemove).toHaveBeenCalledWith(ema.instanceId);
});

/** @jest-environment jsdom */
// B17 + CHART-C091/C129 focused pins — the VISIBLE preset manager section
// mounted in DrawingRail (all-optional props; absent props render the exact
// pre-B17 rail). RED-first: the section does not exist yet.
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import DrawingRail from '../drawings/DrawingRail';
import { PRESET_CAP } from '../drawings/presetSchema';

const drawing = (id, extra = {}) => ({ id, tool: 'trend', ...extra });
const preset = (id, name, extra = {}) => ({
  id, name, tool: 'trend', kind: 'user', starred: false, active: false,
  style: { color: '#7fa6c0', width: 2 }, ...extra,
});

const baseProps = {
  drawings: [drawing('d1', { style: { color: '#7fa6c0', width: 2 } })],
  selectedId: 'd1',
};

test('B17: without preset props the rail renders exactly the pre-B17 rail', () => {
  render(<DrawingRail {...baseProps} />);
  expect(screen.queryByTestId('rail-presets')).not.toBeInTheDocument();
});

test('C091: the preset manager mounts with the scope label and honest preset rows', () => {
  render(<DrawingRail {...baseProps} presetScope="SPY"
    presets={[preset('p1', 'My trend'), preset('p2', 'Fib fav', { tool: 'fib' }), preset('b', 'Built-in trend', { kind: 'built-in' })]}
    onPresetCreate={jest.fn()} onPresetUpdate={jest.fn()} onPresetApply={jest.fn()}
    onPresetToggleStar={jest.fn()} onPresetDelete={jest.fn()} onPresetSetActive={jest.fn()} />);
  expect(screen.getByTestId('rail-presets')).toBeInTheDocument();
  expect(screen.getByTestId('rail-presets-scope')).toHaveTextContent('SPY');
  expect(screen.getAllByTestId('rail-preset')).toHaveLength(3);
  expect(screen.getByTestId('rail-preset-name-p1')).toHaveTextContent('My trend');
  // the built-in row carries its kind and no delete button
  expect(screen.queryByTestId('rail-preset-delete-b')).not.toBeInTheDocument();
  expect(screen.getByTestId('rail-preset-delete-p1')).toBeInTheDocument();
});

test('C091: creating a preset sends the selected drawing style explicitly', () => {
  const onPresetCreate = jest.fn();
  render(<DrawingRail {...baseProps} presetScope="SPY" presets={[]}
    onPresetCreate={onPresetCreate} onPresetUpdate={jest.fn()} onPresetApply={jest.fn()}
    onPresetToggleStar={jest.fn()} onPresetDelete={jest.fn()} onPresetSetActive={jest.fn()} />);
  fireEvent.change(screen.getByTestId('rail-preset-name'), { target: { value: 'My trend' } });
  fireEvent.click(screen.getByTestId('rail-preset-create'));
  expect(onPresetCreate).toHaveBeenCalledWith({ name: 'My trend', tool: 'trend', style: { color: '#7fa6c0', width: 2 } });
});

test('C091: at the cap the create action is refused with an honest notice', () => {
  const fifty = Array.from({ length: PRESET_CAP }, (_, i) => preset('p' + i, 'p' + i));
  render(<DrawingRail {...baseProps} presetScope="SPY" presets={fifty}
    onPresetCreate={jest.fn()} onPresetUpdate={jest.fn()} onPresetApply={jest.fn()}
    onPresetToggleStar={jest.fn()} onPresetDelete={jest.fn()} onPresetSetActive={jest.fn()} />);
  expect(screen.getByTestId('rail-preset-cap')).toBeInTheDocument();
  expect(screen.queryByTestId('rail-preset-create')).not.toBeInTheDocument();
});

test('C129: the dirty dot and Update appear only on the linked preset when it differs', () => {
  const linked = preset('p1', 'My trend');
  const drawingDrifted = drawing('d1', { presetId: 'p1', style: { color: '#e3c16a', width: 2 } }); // width drifted
  render(<DrawingRail drawings={[drawingDrifted]} selectedId="d1" presetScope="SPY"
    presets={[linked, preset('p2', 'Other')]}
    onPresetCreate={jest.fn()} onPresetUpdate={jest.fn()} onPresetApply={jest.fn()}
    onPresetToggleStar={jest.fn()} onPresetDelete={jest.fn()} onPresetSetActive={jest.fn()} />);
  // dirty dot on the linked row only
  expect(screen.getByTestId('rail-preset-dirty-p1')).toBeInTheDocument();
  expect(screen.queryByTestId('rail-preset-dirty-p2')).not.toBeInTheDocument();
  // Update enabled only on the linked preset; the other is disabled
  expect(screen.getByTestId('rail-preset-update-p1')).toBeEnabled();
  expect(screen.getByTestId('rail-preset-update-p2')).toBeDisabled();
});

test('C129: Update sends the selected style to the linked preset only — no autosave anywhere else', () => {
  const onPresetUpdate = jest.fn();
  const linked = preset('p1', 'My trend');
  const drawingDrifted = drawing('d1', { presetId: 'p1', style: { color: '#e3c16a', width: 3 } });
  render(<DrawingRail drawings={[drawingDrifted]} selectedId="d1" presetScope="SPY"
    presets={[linked]}
    onPresetCreate={jest.fn()} onPresetUpdate={onPresetUpdate} onPresetApply={jest.fn()}
    onPresetToggleStar={jest.fn()} onPresetDelete={jest.fn()} onPresetSetActive={jest.fn()} />);
  fireEvent.click(screen.getByTestId('rail-preset-update-p1'));
  expect(onPresetUpdate).toHaveBeenCalledTimes(1);
  expect(onPresetUpdate).toHaveBeenCalledWith('p1', { color: '#e3c16a', width: 3 });
});

test('C129: a clean linked preset has no dirty dot and Update stays disabled', () => {
  const linked = preset('p1', 'My trend');
  const drawingClean = drawing('d1', { presetId: 'p1', style: { color: '#7fa6c0', width: 2 } });
  render(<DrawingRail drawings={[drawingClean]} selectedId="d1" presetScope="SPY"
    presets={[linked]}
    onPresetCreate={jest.fn()} onPresetUpdate={jest.fn()} onPresetApply={jest.fn()}
    onPresetToggleStar={jest.fn()} onPresetDelete={jest.fn()} onPresetSetActive={jest.fn()} />);
  expect(screen.queryByTestId('rail-preset-dirty-p1')).not.toBeInTheDocument();
  expect(screen.getByTestId('rail-preset-update-p1')).toBeDisabled();
});

test('C129/C090: a locked selected drawing refuses preset Apply and Update', () => {
  const linked = preset('p1', 'My trend');
  const lockedDrawing = drawing('d1', { locked: true, presetId: 'p1', style: { color: '#e3c16a', width: 3 } });
  render(<DrawingRail drawings={[lockedDrawing]} selectedId="d1" presetScope="SPY"
    presets={[linked]}
    onPresetCreate={jest.fn()} onPresetUpdate={jest.fn()} onPresetApply={jest.fn()}
    onPresetToggleStar={jest.fn()} onPresetDelete={jest.fn()} onPresetSetActive={jest.fn()} />);
  expect(screen.getByTestId('rail-preset-apply-p1')).toBeDisabled();
  expect(screen.getByTestId('rail-preset-update-p1')).toBeDisabled();
  // the per-drawing style row is refused for locked drawings too (existing behavior)
  expect(screen.queryByTestId('rail-style-row')).not.toBeInTheDocument();
});

test('C091: Apply, star, active and delete report through their callbacks', () => {
  const onPresetApply = jest.fn(), onPresetToggleStar = jest.fn(), onPresetDelete = jest.fn(), onPresetSetActive = jest.fn();
  render(<DrawingRail {...baseProps} presetScope="SPY"
    presets={[preset('p1', 'My trend')]}
    onPresetCreate={jest.fn()} onPresetUpdate={jest.fn()} onPresetApply={onPresetApply}
    onPresetToggleStar={onPresetToggleStar} onPresetDelete={onPresetDelete} onPresetSetActive={onPresetSetActive} />);
  fireEvent.click(screen.getByTestId('rail-preset-apply-p1'));
  expect(onPresetApply).toHaveBeenCalledWith('p1');
  fireEvent.click(screen.getByTestId('rail-preset-star-p1'));
  expect(onPresetToggleStar).toHaveBeenCalledWith('p1');
  fireEvent.click(screen.getByTestId('rail-preset-active-p1'));
  expect(onPresetSetActive).toHaveBeenCalledWith('p1');
  fireEvent.click(screen.getByTestId('rail-preset-delete-p1'));
  expect(onPresetDelete).toHaveBeenCalledWith('p1');
});

test('B17: with no selected drawing the create/apply actions are refused honestly', () => {
  render(<DrawingRail drawings={[drawing('d1')]} selectedId={null} presetScope="SPY"
    presets={[preset('p1', 'My trend')]}
    onPresetCreate={jest.fn()} onPresetUpdate={jest.fn()} onPresetApply={jest.fn()}
    onPresetToggleStar={jest.fn()} onPresetDelete={jest.fn()} onPresetSetActive={jest.fn()} />);
  expect(screen.getByTestId('rail-preset-create')).toBeDisabled();
  expect(screen.getByTestId('rail-preset-apply-p1')).toBeDisabled();
});

test('C091: built-in rows offer no star and no set-active — the fallback tier is not user-managed', () => {
  render(<DrawingRail {...baseProps} presetScope="SPY"
    presets={[preset('b', 'Built-in trend', { kind: 'built-in' }), preset('p1', 'Mine')]}
    onPresetCreate={jest.fn()} onPresetUpdate={jest.fn()} onPresetApply={jest.fn()}
    onPresetToggleStar={jest.fn()} onPresetDelete={jest.fn()} onPresetSetActive={jest.fn()} />);
  expect(screen.queryByTestId('rail-preset-star-b')).not.toBeInTheDocument();
  expect(screen.queryByTestId('rail-preset-active-b')).not.toBeInTheDocument();
  expect(screen.getByTestId('rail-preset-star-p1')).toBeInTheDocument();
  expect(screen.getByTestId('rail-preset-active-p1')).toBeInTheDocument();
});

test('B17: without presetScope the section mounts without a scope line', () => {
  render(<DrawingRail {...baseProps} presets={[]}
    onPresetCreate={jest.fn()} onPresetUpdate={jest.fn()} onPresetApply={jest.fn()}
    onPresetToggleStar={jest.fn()} onPresetDelete={jest.fn()} onPresetSetActive={jest.fn()} />);
  expect(screen.getByTestId('rail-presets')).toBeInTheDocument();
  expect(screen.queryByTestId('rail-presets-scope')).not.toBeInTheDocument();
});

test('C131: the rail offers built-in reset on user rows and labels the store local-only', () => {
  const onPresetReset = jest.fn();
  render(<DrawingRail {...baseProps} presetScope="SPY"
    presets={[preset('b', 'Built-in trend', { kind: 'built-in' }), preset('p1', 'Mine')]}
    onPresetCreate={jest.fn()} onPresetUpdate={jest.fn()} onPresetApply={jest.fn()}
    onPresetToggleStar={jest.fn()} onPresetDelete={jest.fn()} onPresetSetActive={jest.fn()}
    onPresetReset={onPresetReset} />);
  // Reset offered on user rows only — built-ins ARE the default
  expect(screen.getByTestId('rail-preset-reset-p1')).toBeInTheDocument();
  expect(screen.queryByTestId('rail-preset-reset-b')).not.toBeInTheDocument();
  fireEvent.click(screen.getByTestId('rail-preset-reset-p1'));
  expect(onPresetReset).toHaveBeenCalledWith('p1');
  // the store is explicitly labelled local-only (no cloud/account claim)
  expect(screen.getByTestId('rail-presets-local')).toHaveTextContent(/local/i);
  expect(screen.getByTestId('rail-presets-local')).toHaveTextContent(/no cloud/i);
});

test('C131: without onPresetReset the rail renders no reset buttons (additive optional prop)', () => {
  render(<DrawingRail {...baseProps} presetScope="SPY"
    presets={[preset('p1', 'Mine')]}
    onPresetCreate={jest.fn()} onPresetUpdate={jest.fn()} onPresetApply={jest.fn()}
    onPresetToggleStar={jest.fn()} onPresetDelete={jest.fn()} onPresetSetActive={jest.fn()} />);
  expect(screen.queryByTestId('rail-preset-reset-p1')).not.toBeInTheDocument();
  // the local-only label still shows whenever the section mounts
  expect(screen.getByTestId('rail-presets-local')).toBeInTheDocument();
});

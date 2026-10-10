import { TOOLS, createDrawing, magnet, reduceDrawings } from '../drawings/drawingReducer';
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

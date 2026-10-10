import { createLayout, serialize, migrate, sanitizeImport } from '../persistence/layoutSchema';
import { saveLocal, loadLocal, _clear } from '../persistence/layoutStore';
test('false/zero roundtrip + corrupt recovery + caps + proto/scripts refused', () => {
  _clear();
  const layout = createLayout({ showGrid: false, opacity: 0 });
  const text = serialize(layout);
  expect(JSON.parse(text).showGrid).toBe(false);
  expect(migrate('{{{').recovered).toBe(true);
  expect(() => serialize({ ...layout, apiKey: 'x' })).toThrow('secrets-refused');
  expect(() => sanitizeImport(JSON.parse('{"__proto__":1}'))).toThrow('proto-refused');
  expect(() => sanitizeImport({ script: 'evil()' })).toThrow('scripts-refused');
  saveLocal('a', layout);
  expect(loadLocal('a')).toBe(text);
});

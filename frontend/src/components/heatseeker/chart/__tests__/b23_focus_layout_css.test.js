import fs from 'fs';
import path from 'path';

// jsdom does not calculate grid geometry; the real-browser check verifies it.
test('focus scopes the external rail and grid overrides to the owning layout', () => {
  const css = fs.readFileSync(path.join(__dirname, '..', 'stock-chrome.css'), 'utf8');
  expect(css).toMatch(/\.heatseeker-layout:has\(\.price-node-focused\)\s*>\s*\.heatseeker-sidebar-left\s*\{\s*display:\s*none\s*!important\s*;\s*\}/);
  expect(css).toMatch(/\.heatseeker-layout:has\(\.price-node-focused\)\s*\{\s*grid-template-columns:\s*0\s+minmax\(0,\s*1fr\)\s*;\s*\}/);
});

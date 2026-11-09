const fs = require('fs');
const path = require('path');

test('multi-pane grids stack at the observed 961px narrow-desktop boundary', () => {
  const css = fs.readFileSync(path.join(__dirname, '..', 'ChartWorkspace.css'), 'utf8');
  const responsiveBlocks = [...css.matchAll(/@media\s*\(max-width:\s*(\d+)px\)\s*\{([\s\S]*?)\n\}/g)];
  const paneBlock = responsiveBlocks.find(([, , body]) => body.includes('.pane-layout[class]'));
  expect(paneBlock).toBeDefined();
  expect(Number(paneBlock[1])).toBeGreaterThanOrEqual(961);
  expect(paneBlock[2]).toMatch(/\.pane-layout\[class\]\s*\{\s*grid-template-columns:\s*minmax\(0,\s*1fr\);/);
  expect(paneBlock[2]).toMatch(/\.pane-layout\[class\]\s*>\s*\.pane-slot\s*\{\s*grid-column:\s*auto;\s*grid-row:\s*auto;/);
});

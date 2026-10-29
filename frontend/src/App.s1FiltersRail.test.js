/** @jest-environment jsdom */
// S1 optional filter rail — CSS contract pins (the real geometry proof is the
// live 1470x950 / 1024x768 measurement on the built candidate):
// 1. At desktop the filters rail HONORS the existing Filters toggle — the bare
//    selector must not force `display: block !important`, so the closed
//    (default) state gives the chart the full main column.
// 2. The toggle bar (Filters / Analytics buttons) must stay REACHABLE at
//    desktop — the >=1024 block may not hide it.
const fs = require('fs');
const path = require('path');

const css = fs.readFileSync(path.join(__dirname, 'App.css'), 'utf8');

// Extract every @media block by brace matching.
function mediaBlocks(source, query) {
  const blocks = [];
  const re = /@media\s*\([^)]*\)/g;
  let m;
  while ((m = re.exec(source)) !== null) {
    if (!m[0].includes(query)) continue;
    let depth = 0, i = source.indexOf('{', m.index);
    for (let j = i; j < source.length; j += 1) {
      if (source[j] === '{') depth += 1;
      else if (source[j] === '}') { depth -= 1; if (depth === 0) { blocks.push(source.slice(i + 1, j)); break; } }
    }
    re.lastIndex = i;
  }
  return blocks;
}

test('desktop rail honors the Filters toggle instead of forcing itself on', () => {
  const desktop = mediaBlocks(css, 'min-width: 1024px');
  expect(desktop.length).toBeGreaterThan(0);
  const rail = desktop.map(b => b.match(/\.heatseeker-sidebar-left\s*\{[^}]*\}/)).find(Boolean);
  expect(rail).not.toBeNull();
  // the desktop bare rule HIDES the rail (the closed default) and never
  // forces it on; the tablet band keeps its own incumbent rule untouched.
  expect(rail[0]).toMatch(/display:\s*none\s*!important/);
  expect(rail[0]).not.toMatch(/display:\s*block\s*!important/);
  // the .open rule shows the static filters column at desktop
  const open = [];
  for (const b of desktop) {
    for (const m of b.matchAll(/\.heatseeker-sidebar-left\.open\s*\{[^}]*\}/g)) open.push(m[0]);
  }
  expect(open.some(r => /display:\s*block\s*!important/.test(r))).toBe(true);
  // and no desktop rule pins the open rail to the mobile fixed overlay
  for (const r of open) expect(r).not.toMatch(/position:\s*fixed/);
});

test('the Filters toggle bar stays reachable at desktop widths', () => {
  const desktopBlock = css.slice(css.indexOf('@media (min-width: 1024px)'));
  const barRule = desktopBlock.match(/\.mobile-toggle-bar\s*\{[^}]*\}/);
  if (barRule) {
    expect(barRule[0]).not.toMatch(/display:\s*none/);
  }
  // a visible desktop toggle-bar rule must exist somewhere after the block
  expect(css).toMatch(/\.mobile-toggle-bar\s*\{[^}]*display:\s*(flex|block|grid)/);
});

/**
 * App.js keyboard invariant: global single-key shortcuts (page/view/mode
 * switches, arrow-key ticker cycling) must yield when focus is inside the
 * strike matrix or a modal dialog. Proven browser defect: ArrowDown on a
 * focused gridcell cycled SPY→QQQ and unmounted the matrix under the user.
 * Source-text invariant (same precedent as App.egress-invariant.test.js):
 * the keydown handler returns early for [role="grid"] / [role="dialog"]
 * targets before the shortcut switch.
 */
const fs = require('fs');
const path = require('path');

const APP_JS_PATH = path.join(__dirname, 'App.js');

describe('App.js keyboard shortcut invariant', () => {
  let source;

  beforeAll(() => {
    source = fs.readFileSync(APP_JS_PATH, 'utf8');
  });

  test('keydown handler yields to matrix and dialog focus before the shortcut switch', () => {
    const handler = source.match(/const handler = \(e\) => \{[\s\S]*?switch \(e\.key\)/);
    expect(handler).not.toBeNull();
    expect(handler[0]).toMatch(/closest\('\[role="grid"\], \[role="dialog"\]'\)/);
  });
});

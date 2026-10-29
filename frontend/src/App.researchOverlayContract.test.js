/** @jest-environment jsdom */
// Global-overlay lease contract pins (root's Oct 27 09:58 directive + the
// color-cascade correction). The live pixel proof runs on the built candidate
// per the browser-live-proof skill; these pins keep the lease's scope honest
// at the source level:
// 1. The PWA marketing banner does NOT mount on the Stock/Market research
//    routes (heatseeker, trinity) — it stays available on every other page.
// 2. The research routes' raw native controls adopt the EXISTING dark tokens
//    (route-scoped to .heatseeker-layout/.legacy-theme only — no global
//    native-input rewrite, no second theme layer).
// 3. NO new --floww-research-* token layer was introduced (root's cascade
//    correction: reuse the existing tokens).
const fs = require('fs');
const path = require('path');

const appJs = fs.readFileSync(path.join(__dirname, 'App.js'), 'utf8');
const appCss = fs.readFileSync(path.join(__dirname, 'App.css'), 'utf8');

test('the PWA install banner is gated OFF the two research routes but stays mounted elsewhere', () => {
  // The banner mount must be conditional on the page, excluding the research routes.
  const gated = appJs.match(/\{!\["heatseeker",\s*"trinity"\]\.includes\(page\)\s*&&\s*<PWAInstallBanner\s*\/>\}/);
  expect(gated).not.toBeNull();
  // And no ungated mount remains anywhere in the file.
  const allMounts = appJs.match(/<PWAInstallBanner\s*\/>/g) || [];
  expect(allMounts.length).toBe(1);
  expect(appJs.indexOf(allMounts[0])).toBeGreaterThan(appJs.indexOf('includes(page)'));
});

test('the research routes carry the native-control rule scoped to their page roots', () => {
  // Route-scoped only: the selectors must target .heatseeker-layout/.legacy-theme.
  const rule = appCss.match(/\.heatseeker-layout select,[^}]*\{[^}]*\}/s);
  expect(rule).not.toBeNull();
  expect(rule[0]).toContain('.legacy-theme select');
  expect(rule[0]).toContain('.legacy-theme input');
  // Existing tokens with root's fallback chain — no new palette hard-codes.
  expect(rule[0]).toContain('var(--floww-surface, var(--panel, #111111))');
  expect(rule[0]).toContain('var(--text, #d5dde5)');
  expect(rule[0]).toContain('var(--floww-line, var(--border-2, #454545))');
  // The rule must NOT leak to every input on every route (no bare `input {` global).
  expect(rule[0].startsWith('.heatseeker-layout')).toBe(true);
});

test('no second research-token theme layer was added (root color-cascade correction)', () => {
  expect(appCss).not.toMatch(/--floww-research-/);
  expect(appJs).not.toMatch(/--floww-research-/);
});

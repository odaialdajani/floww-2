import fs from 'fs';
import path from 'path';
import React from 'react';
import { render, screen } from '@testing-library/react';
import RecordedPriceChart from '../../RecordedPriceChart';

// The four-up geometry defect: "Chart focus" and "Latest candle" painted
// beyond their pane's right edge. jsdom computes no layout and no container
// query, so the layout proof lives in the compiled browser acceptance; these
// pins bind the SHIPPED narrow-container rule to the real DOM nodes it
// targets, so the rule cannot silently lose the elements it governs.
const CSS_PATH = path.join(__dirname, '..', 'stock-chrome.css');

function narrowContainerBlock(css) {
  const start = css.indexOf('@container (max-width: 900px)');
  expect(start).toBeGreaterThan(-1);
  // The container closes at the first column-zero brace; its inner rules are
  // single-line, so no inner "\n}" can be mistaken for the container's own.
  const end = css.indexOf('\n}', start);
  expect(end).toBeGreaterThan(start);
  return css.slice(start, end + 2);
}

function ruleBody(cssText, selector) {
  const at = cssText.indexOf(selector);
  if (at < 0) return null;
  const open = cssText.indexOf('{', at);
  const close = cssText.indexOf('}', open);
  if (open < 0 || close < 0) return null;
  return cssText.slice(open + 1, close);
}

test('the narrow-pane container lets the action and replay groups wrap inside the pane', () => {
  const css = fs.readFileSync(CSS_PATH, 'utf8');
  const block = narrowContainerBlock(css);

  const dock = ruleBody(block, '.recorded-chart-tools .stock-dock-actions,');
  expect(dock).not.toBeNull();
  expect(dock).toMatch(/flex-wrap:\s*wrap/);
  expect(dock).toMatch(/min-width:\s*0/);
  expect(dock).toMatch(/max-width:\s*100%/);
  expect(dock).toMatch(/box-sizing:\s*border-box/);

  const replayInline = ruleBody(block, '.recorded-chart-tools .recorded-chart-replay-inline');
  expect(replayInline).not.toBeNull();
  expect(replayInline).toMatch(/flex-wrap:\s*wrap/);
  expect(replayInline).toMatch(/min-width:\s*0/);
  expect(replayInline).toMatch(/max-width:\s*100%/);

  // The replay group's own nowrap rule must be overridden inside the
  // container, or "Latest candle" still overflows the pane.
  const replay = ruleBody(block, '.recorded-chart-tools .price-history-replay.price-history-replay');
  expect(replay).not.toBeNull();
  expect(replay).toMatch(/flex-wrap:\s*wrap/);
  expect(replay).toMatch(/max-width:\s*100%/);

  // A wrapped button keeps its own hit area instead of collapsing.
  const buttons = ruleBody(block, '.recorded-chart-tools .stock-dock-actions > button,');
  expect(buttons).not.toBeNull();
  expect(buttons).toMatch(/flex:\s*0 0 auto/);
});

test('the narrow-pane rule still leaves the wide-pane command row unwrapped', () => {
  const css = fs.readFileSync(CSS_PATH, 'utf8');
  // The wide rule is the doubled-class declaration OUTSIDE the container.
  const wide = ruleBody(css, '.recorded-chart-tools.recorded-chart-tools {');
  expect(wide).not.toBeNull();
  expect(wide).toMatch(/flex-wrap:\s*nowrap/);
  // The narrow container is a separate, later block: it must not have been
  // folded into the wide rule.
  expect(css.indexOf('@container (max-width: 900px)')).toBeGreaterThan(css.indexOf('.recorded-chart-tools.recorded-chart-tools {'));
});

test('the groups the narrow-pane rule targets are the real DOM holders of the clipped controls', () => {
  const frames = Array.from({ length: 12 }, (_, i) => ({
    time: new Date(Date.UTC(2026, 9, 1, 13, 30 + i * 30)).toISOString(),
    open: 100 + i, high: 102 + i, low: 99 + i, close: 101 + i, nodes: [], duration_seconds: 1800,
  }));
  render(
    <RecordedPriceChart
      ticker="SPY"
      frames={frames}
      toolbarControls={
        <span className="stock-dock-actions" data-testid="dock-actions">
          <button type="button" className="stock-dock-btn">Chart focus</button>
        </span>
      }
      replayControls={
        <div className="price-history-replay">
          <button type="button">Play replay</button>
          <button type="button">Latest candle</button>
        </div>
      }
    />
  );
  const row = screen.getByTestId('chart-control-row');
  expect(row.classList.contains('recorded-chart-tools')).toBe(true);

  // "Chart focus" is a direct button child of the dock-actions group.
  const dock = screen.getByTestId('dock-actions');
  expect(dock.classList.contains('stock-dock-actions')).toBe(true);
  expect(dock.querySelectorAll(':scope > button')).toHaveLength(1);
  expect(screen.getByRole('button', { name: 'Chart focus' }).closest('.stock-dock-actions')).toBe(dock);

  // "Latest candle" lives inside .price-history-replay, which the wrapper
  // span .recorded-chart-replay-inline carries.
  const replayRow = screen.getByTestId('chart-replay-row');
  expect(replayRow.classList.contains('recorded-chart-replay-inline')).toBe(true);
  const latest = screen.getByRole('button', { name: 'Latest candle' });
  expect(latest.closest('.price-history-replay')).not.toBeNull();
  expect(replayRow.contains(latest)).toBe(true);
});

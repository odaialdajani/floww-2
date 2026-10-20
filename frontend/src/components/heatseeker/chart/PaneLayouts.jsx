import React from 'react';
// B11 pane layouts: named presets with real pane counts, a focusable slot per
// pane, and phone stacking (single column under 620px). The manager renders
// REAL chart panes through renderPane — layout metadata alone does not count.
export const LAYOUT_PRESETS = [
  { id: 'single', label: 'Single pane', panes: 1, className: 'pane-layout-single' },
  { id: 'split', label: 'Split · 2 panes', panes: 2, className: 'pane-layout-split' },
  { id: 'three', label: 'Three panes', panes: 3, className: 'pane-layout-three' },
];
export function layoutById(id) {
  return LAYOUT_PRESETS.find(l => l.id === id) || LAYOUT_PRESETS[0];
}
export default function PaneLayouts({ layout, panes, onFocus, renderPane }) {
  const def = layoutById(layout);
  const visible = panes.slice(0, def.panes);
  return (
    <div
      data-testid="pane-layout"
      data-layout={def.id}
      data-panes={def.panes}
      className={'pane-layout ' + def.className + ' pane-count-' + def.panes}
    >
      {visible.map(pane => (
        <div key={pane.id} className={'pane-slot' + (pane.focused ? ' pane-slot-focused' : '')} data-pane-id={pane.id}>
          <button
            type="button"
            className="pane-focus-btn"
            data-testid={'focus-' + pane.id}
            aria-pressed={pane.focused}
            onClick={() => onFocus(pane.id)}
          >
            {pane.focused ? 'Focused' : 'Focus'} {pane.symbol}
          </button>
          {renderPane(pane)}
        </div>
      ))}
    </div>
  );
}

import React from 'react';
// B11 pane layouts: named presets with real pane counts, a focusable slot per
// pane, and narrow/high-zoom stacking through the workspace CSS. The manager renders
// REAL chart panes through renderPane — layout metadata alone does not count.
import { layoutById } from './paneLayoutPresets';
export { LAYOUT_PRESETS, layoutById } from './paneLayoutPresets';
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

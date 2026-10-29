import React from "react";

// Stock contextual right workspace (visual-reset-20261025 brief): ONE bounded
// dock for the current selection — indicators/studies and the measured-pane
// controls, pane data actions, and the review workflow. Stable tabs, explicit
// close/reopen, authoritative selection owned by the caller. Docked while the
// chart keeps useful width; the CSS switches it to a controlled overlay on
// narrow desktop. No data of its own — every tab renders caller-provided
// content, so unavailable data stays honestly unavailable.
const TABS = [
  { id: "indicators", label: "Indicators" },
  { id: "drawings", label: "Drawings" },
  { id: "data", label: "Data" },
  { id: "review", label: "Review" },
];

export default function StockInspector({ open = true, activeTab = "indicators", onTabChange, onClose, indicators = null, drawings = null, data = null, review = null, counts = null }) {
  const body = activeTab === "drawings" ? drawings : activeTab === "data" ? data : activeTab === "review" ? review : indicators;
  return (
    <aside className="stock-inspector" data-testid="stock-inspector" data-open={!!open} data-active-tab={activeTab} aria-label="Stock workspace">
      <header className="stock-inspector-head">
        <span className="stock-inspector-title">Workspace</span>
        <div className="stock-inspector-tabs" role="tablist" aria-label="Workspace tabs">
          {TABS.map(tab => (
            <button key={tab.id} type="button" role="tab" aria-selected={activeTab === tab.id}
              data-testid={"stock-inspector-tab-" + tab.id}
              className={"stock-inspector-tab" + (activeTab === tab.id ? " is-active" : "")}
              onClick={() => { onTabChange?.(tab.id); }}>
              {tab.label}{counts && counts[tab.id] ? ` · ${counts[tab.id]}` : ""}
            </button>
          ))}
        </div>
        {onClose && <button type="button" className="stock-inspector-close" data-testid="stock-inspector-close" aria-label="Close workspace" onClick={onClose}>×</button>}
      </header>
      {open ? (
        /* Mount-once tab panels: every tab's content stays mounted so its
           controls/testids are always in the DOM; ONLY the active panel is
           painted (hidden panels are display:none) — the canonical
           stock-inspector-body testid rides the ACTIVE panel alone. */
        TABS.map(tab => {
          const content = tab.id === "drawings" ? drawings : tab.id === "data" ? data : tab.id === "review" ? review : indicators;
          return (
            <div key={tab.id} className="stock-inspector-body" data-testid={activeTab === tab.id ? "stock-inspector-body" : "stock-inspector-panel-" + tab.id}
              data-tab={tab.id} role="tabpanel" hidden={activeTab !== tab.id}>
              {content || <p className="stock-inspector-empty">No content for this tab.</p>}
            </div>
          );
        })
      ) : (
        <div className="stock-inspector-closed" data-testid="stock-inspector-closed">
          <span>Workspace closed — open a tab from the chart row.</span>
        </div>
      )}
    </aside>
  );
}

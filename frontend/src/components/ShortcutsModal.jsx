import React, { useState, useEffect } from "react";

const SHORTCUTS = [
  { category: "Navigation", items: [
    { key: "1", desc: "Market view" },
    { key: "2", desc: "Stock chart" },
    { key: "3", desc: "Portfolio" },
    { key: "4 / J", desc: "Trade Journal" },
    { key: "↑/↓", desc: "Cycle tickers" },
  ]},
  { category: "Views", items: [
    { key: "G", desc: "2D Grid heatmap" },
    { key: "B", desc: "Bar heatmap" },
    { key: "C", desc: "Options chain" },
  ]},
  { category: "Modes", items: [
    { key: "D", desc: "Day mode (±15%)" },
    { key: "S", desc: "Swing mode (±25%)" },
    { key: "X", desc: "Scalp mode (0DTE, ±2%)" },
  ]},
  { category: "Overlays", items: [
    { key: "E", desc: "GEX overlay" },
    { key: "V", desc: "VEX overlay" },
    { key: "H", desc: "Charm overlay" },
  ]},
];

export function ShortcutsModal() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const handler = (e) => {
      if (e.key === "?" && !e.target.matches("input, select, textarea")) {
        e.preventDefault();
        setOpen((o) => !o);
      }
      if (e.key === "Escape" && open) {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(0,0,0,0.7)" }}
      onClick={() => setOpen(false)}
    >
      <div
        className="panel p-4 max-w-lg w-[90%] max-h-[80vh] overflow-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-center mb-3">
          <div className="text-lg font-bold">Keyboard Shortcuts</div>
          <button onClick={() => setOpen(false)} className="btn text-[10px]">✕ Esc</button>
        </div>
        <div className="grid grid-cols-2 gap-4">
          {SHORTCUTS.map((group) => (
            <div key={group.category}>
              <div className="label mb-1">{group.category}</div>
              <div className="space-y-0.5">
                {group.items.map((item) => (
                  <div key={item.key} className="flex justify-between text-[11px]">
                    <span className="text-slate-400">{item.desc}</span>
                    <kbd className="mono bg-slate-800 px-1.5 py-0.5 rounded text-[10px] text-slate-300 border border-slate-700">
                      {item.key}
                    </kbd>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
        <div className="text-[9px] text-slate-600 mt-3 text-center">
          Press <kbd className="mono bg-slate-800 px-1 py-0.5 rounded text-[8px] border border-slate-700">?</kbd> to toggle this panel
        </div>
      </div>
    </div>
  );
}

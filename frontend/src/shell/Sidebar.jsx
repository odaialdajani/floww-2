import { useState, useEffect } from "react";
import { NAV_ITEMS, SIDEBAR_KEY } from "./navConfig";

// Simple SVG icon map — no external deps needed
const ICONS = {
  "layout-dashboard": (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect width="7" height="9" x="3" y="3" rx="1"/><rect width="7" height="5" x="14" y="3" rx="1"/><rect width="7" height="9" x="14" y="12" rx="1"/><rect width="7" height="5" x="3" y="16" rx="1"/></svg>
  ),
  "sparkles": (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M11.017 2.814a1 1 0 0 1 1.966 0l1.051 5.558a2 2 0 0 0 1.594 1.594l5.558 1.051a1 1 0 0 1 0 1.966l-5.558 1.051a2 2 0 0 0-1.594 1.594l-1.051 5.558a1 1 0 0 1-1.966 0l-1.051-5.558a2 2 0 0 0-1.594-1.594l-5.558-1.051a1 1 0 0 1 0-1.966l5.558-1.051a2 2 0 0 0 1.594-1.594z"/><path d="M20 2v4"/><path d="M22 4h-4"/><circle cx="4" cy="20" r="2"/></svg>
  ),
  "file-text": (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z"/><path d="M14 2v5a1 1 0 0 0 1 1h5"/><path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/></svg>
  ),
  "bell": (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M10.268 21a2 2 0 0 0 3.464 0"/><path d="M3.262 15.326A1 1 0 0 0 4 17h16a1 1 0 0 0 .74-1.673C19.41 13.956 18 12.499 18 8A6 6 0 0 0 6 8c0 4.499-1.411 5.956-2.738 7.326"/></svg>
  ),
  "grid": (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/></svg>
  ),
  "search": (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
  ),
  "calendar": (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>
  ),
  "activity": (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2"/></svg>
  ),
  "list": (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><line x1="8" x2="21" y1="6" y2="6"/><line x1="8" x2="21" y1="12" y2="12"/><line x1="8" x2="21" y1="18" y2="18"/><line x1="3" x2="3.01" y1="6" y2="6"/><line x1="3" x2="3.01" y1="12" y2="12"/><line x1="3" x2="3.01" y1="18" y2="18"/></svg>
  ),
  "trending-up": (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>
  ),
  "bar-chart": (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M3 3v16a2 2 0 0 0 2 2h16"/><path d="M7 16h.01"/><path d="M11 12h.01"/><path d="M15 16h.01"/><path d="M19 8h.01"/></svg>
  ),
  "layers": (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="m22.54 12.43-1.42-.65-8.28 3.78a2 2 0 0 1-1.66 0l-8.29-3.78-1.42.65a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="m22.54 17.43-1.42-.65-8.28 3.78a2 2 0 0 1-1.66 0l-8.29-3.78-1.42.65a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/></svg>
  ),
  "alert-triangle": (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>
  ),
  // Legacy icons (simple fallback)
  "default": (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/></svg>
  ),
};

function getIcon(id) {
  return ICONS[id] || ICONS["default"];
}

export default function Sidebar({ page, onNavigate, userEmail, userTier }) {
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(SIDEBAR_KEY) === "true");
  const [legacyExpanded, setLegacyExpanded] = useState(false);
  useEffect(() => {
    localStorage.setItem(SIDEBAR_KEY, String(collapsed));
    document.documentElement.setAttribute("data-sidebar-collapsed", String(collapsed));
  }, [collapsed]);

  // Group nav items by their group
  const groups = [];
  let currentGroup = null;
  NAV_ITEMS.forEach(item => {
    if (item.group !== currentGroup) {
      currentGroup = item.group;
      groups.push({ name: currentGroup, items: [] });
    }
    groups[groups.length - 1].items.push(item);
  });

  return (
    <aside
      data-collapsed={collapsed}
      className="print-hide fixed left-0 top-0 z-40 flex h-screen flex-col border-r"
      style={{
        width: collapsed ? 64 : 240,
        background: "var(--bg-sidebar)",
        borderColor: "var(--border-c)",
        transition: "width 180ms",
        fontFamily: "var(--font-sans)",
      }}
    >
      {/* Logo / Brand */}
      <div
        className="flex items-center gap-2.5 px-4 pt-3 pb-3"
        style={{ borderBottom: "1px solid var(--border-c)" }}
      >
        <div
          className="flex h-7 w-7 items-center justify-center rounded-md"
          style={{ background: "var(--gold-dim)", border: "1px solid var(--gold-border)" }}
        >
          <span className="display font-bold text-sm" style={{ color: "var(--gold)" }}>α</span>
        </div>
        {!collapsed && (
          <span
            className="display font-bold tracking-[0.12em]"
            style={{ fontSize: 13, color: "var(--text-primary)" }}
          >
            ALPHA POD
          </span>
        )}
        <button
          type="button"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!collapsed}
          title="Collapse sidebar"
          onClick={() => setCollapsed(c => !c)}
          className="ml-auto flex h-7 w-7 items-center justify-center rounded-md transition-colors"
          style={{
            color: "var(--text-tertiary)",
            background: "rgba(255,255,255,0.04)",
            border: "1px solid var(--border-c)",
            cursor: "pointer",
          }}
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="m15 18-6-6 6-6"/>
          </svg>
        </button>
      </div>

      {/* Navigation */}
      <nav className="ap-mobile-scroll flex-1 overflow-y-auto p-2 pt-3">
        {groups.map((group, gi) => {
          const isLegacy = group.name === "Legacy";
          const showItems = !isLegacy || legacyExpanded;
          return (
            <div key={gi} className="mb-1">
              {!collapsed && (
                <button
                  type="button"
                  onClick={isLegacy ? () => setLegacyExpanded(v => !v) : undefined}
                  className="display flex w-full items-center gap-1.5 px-3 pt-3 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.12em]"
                  style={{
                    color: "var(--text-quaternary)",
                    background: "transparent",
                    border: "none",
                    cursor: isLegacy ? "pointer" : "default",
                    textAlign: "left",
                  }}
                >
                  {isLegacy && (
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      width="10"
                      height="10"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      style={{
                        transform: legacyExpanded ? "rotate(0deg)" : "rotate(-90deg)",
                        transition: "transform 150ms",
                        flexShrink: 0,
                      }}
                    >
                      <path d="m6 9 6 6 6-6"/>
                    </svg>
                  )}
                  {group.name}
                </button>
              )}
              {showItems && group.items.map(item => {
                const active = page === item.id;
                return (
                  <button
                    key={item.id}
                    onClick={() => onNavigate(item.id)}
                    aria-label={group.name === "AlphaPod Live" ? `${item.label} (AlphaPod Live)` : undefined}
                    aria-current={active ? "page" : undefined}
                    className="group relative flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium transition-colors"
                    style={{
                      width: "100%",
                      color: active ? "var(--text-primary)" : "var(--text-secondary)",
                      background: active ? "rgba(255,255,255,0.06)" : "transparent",
                      border: "none",
                      cursor: "pointer",
                      textAlign: "left",
                    }}
                  >
                    <span className="nav-icon" style={{ flexShrink: 0, color: active ? "var(--gold)" : "inherit" }}>
                      {getIcon(item.icon)}
                    </span>
                    {!collapsed && <span className="truncate">{item.label}</span>}
                    {!collapsed && item.badge === "NEW" && (
                      <span
                        className="mono ml-auto rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider"
                        style={{ background: "var(--green-dim)", color: "var(--green)" }}
                      >
                        NEW
                      </span>
                    )}
                    {!collapsed && item.badge === "LIVE" && item.liveDot && (
                      <span className="nav-live-dot" />
                    )}
                    {!collapsed && item.badge === "LIVE" && !item.liveDot && (
                      <span
                        className="mono ml-auto rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider"
                        style={{ background: "var(--green-dim)", color: "var(--green)" }}
                      >
                        LIVE
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          );
        })}
      </nav>

      {/* User chip at bottom */}
      {!collapsed && userEmail && (
        <div
          className="flex items-center gap-2 px-4 py-3"
          style={{ borderTop: "1px solid var(--border-c)" }}
        >
          <div
            className="flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-bold"
            style={{ background: "var(--gold-dim)", color: "var(--gold)" }}
          >
            {userEmail[0].toUpperCase()}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[11px] truncate" style={{ color: "var(--text-secondary)" }}>
              {userEmail}
            </div>
          </div>
          {userTier && (
            <span
              className="mono text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded"
              style={{ background: "var(--gold-dim)", color: "var(--gold)" }}
            >
              {userTier}
            </span>
          )}
        </div>
      )}
    </aside>
  );
}

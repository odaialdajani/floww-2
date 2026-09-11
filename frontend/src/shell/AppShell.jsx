import { useState, useEffect } from "react";
import Sidebar from "./Sidebar";
import AgentProvider from "../agent/AgentProvider";
import AgentPanel from "../agent/AgentPanel";
import AgentCommandBar from "../agent/AgentCommandBar";
import { SIDEBAR_KEY } from "./navConfig";

function readCollapsed() {
  // Same source the Sidebar itself reads (2026-09-04): the DOM attribute
  // handshake alone can disagree on first paint (attribute unset until the
  // Sidebar mounts), leaving a ~176px dead gutter beside the rail.
  try {
    const v = localStorage.getItem(SIDEBAR_KEY);
    if (v != null) return v === "true";
  } catch { /* private mode — fall through to the attribute */ }
  return document.documentElement.getAttribute("data-sidebar-collapsed") === "true";
}

function useSidebarCollapsed() {
  const [collapsed, setCollapsed] = useState(readCollapsed);
  useEffect(() => {
    const observer = new MutationObserver((mutations) => {
      for (const m of mutations) {
        if (m.type === "attributes" && m.attributeName === "data-sidebar-collapsed") {
          setCollapsed(document.documentElement.getAttribute("data-sidebar-collapsed") === "true");
        }
      }
    });
    observer.observe(document.documentElement, { attributes: true });
    return () => observer.disconnect();
  }, []);
  return collapsed;
}

export default function AppShell({ page, onNavigate, children, userEmail, userTier }) {
  const collapsed = useSidebarCollapsed();
  return (
    <AgentProvider>
    <div className="min-h-screen" style={{ background: "var(--bg-page)" }}>
      <Sidebar page={page} onNavigate={onNavigate} userEmail={userEmail} userTier={userTier} />
      <main
        style={{
          marginLeft: collapsed ? 64 : 240,
          minWidth: 0,
          display: "flex",
          flexDirection: "column",
          minHeight: "100vh",
          transition: "margin-left 180ms",
        }}
      >
        {children}
      </main>
      <AgentPanel />
      <AgentCommandBar />
    </div>
    </AgentProvider>
  );
}

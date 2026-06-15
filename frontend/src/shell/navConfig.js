export const SIDEBAR_KEY = "apw.sidebarCollapsed";

// legacy:true tabs render inside a .legacy-theme wrapper (preserved look)
// These are the pages we keep from the original floww project
export const NAV_ITEMS = [
  // Overview
  { id: "dashboard",  label: "Dashboard",  group: "Overview", icon: "layout-dashboard" },

  // Alpha Flow
  { id: "alpha-flow",  label: "Alpha Flow",  group: "Alpha Flow", icon: "sparkles", badge: "NEW" },
  { id: "daily-report", label: "Daily Report", group: "Alpha Flow", icon: "file-text", badge: "NEW" },
  { id: "flow-alerts", label: "Flow Alerts", group: "Alpha Flow", icon: "bell", badge: "LIVE", liveDot: true },
  { id: "heatmaps",    label: "Heatmaps",    group: "Alpha Flow", icon: "grid" },

  // Analysis
  { id: "ticker-analysis", label: "Ticker Analysis", group: "Analysis", icon: "search", badge: "NEW" },
  { id: "earnings",       label: "Earnings",       group: "Analysis", icon: "calendar" },

  // Kairos Algo
  { id: "signals",     label: "Active Signals", group: "Kairos Algo", icon: "activity" },
  { id: "trade-log",   label: "Trade Log",      group: "Kairos Algo", icon: "list" },
  { id: "performance", label: "Performance",    group: "Kairos Algo", icon: "trending-up" },

  // SPX
  { id: "spx-gex",    label: "SPX GEX",    group: "SPX", icon: "bar-chart", badge: "NEW" },
  { id: "key-levels", label: "Key Levels", group: "SPX", icon: "layers" },
  { id: "spx-alerts", label: "SPX Alerts", group: "SPX", icon: "alert-triangle" },

  // AlphaPod Live — captured pages served from alphapod-hub (localhost:3456)
  { id: "ap-flow-alerts",  label: "Flow Alerts",   group: "AlphaPod Live", icon: "bell",         badge: "LIVE", liveDot: true, aphub: "/captured/flow-alerts-live.html" },
  { id: "ap-spx-gex",      label: "SPX GEX",       group: "AlphaPod Live", icon: "bar-chart",    aphub: "/captured/spx-gex-live.html" },
  { id: "ap-alpha-flow",   label: "Alpha Flow",    group: "AlphaPod Live", icon: "sparkles",     aphub: "/captured/alpha-flow-live.html" },
  { id: "ap-daily-report", label: "Daily Report",  group: "AlphaPod Live", icon: "file-text",    aphub: "/captured/daily-report-live.html" },
  { id: "ap-heatmaps",     label: "Heatmaps",      group: "AlphaPod Live", icon: "grid",         aphub: "/captured/heatmaps-live.html" },
  { id: "ap-signals",      label: "Signals",       group: "AlphaPod Live", icon: "activity",     aphub: "/captured/signals-live.html" },
  { id: "ap-trade-log",    label: "Trade Log",     group: "AlphaPod Live", icon: "list",         aphub: "/captured/trade-log-live.html" },
  { id: "ap-performance",  label: "Performance",   group: "AlphaPod Live", icon: "trending-up",  aphub: "/captured/performance-live.html" },
  { id: "ap-key-levels",   label: "Key Levels",    group: "AlphaPod Live", icon: "layers",       aphub: "/captured/key-levels-live.html" },
  { id: "ap-earnings",     label: "Earnings",      group: "AlphaPod Live", icon: "calendar",     aphub: "/captured/earnings-live.html" },
  { id: "ap-spx-alerts",   label: "SPX Alerts",    group: "AlphaPod Live", icon: "alert-triangle", aphub: "/captured/spx-alerts.html" },
  { id: "ap-ticker-nvda",  label: "NVDA Deep Dive",group: "AlphaPod Live", icon: "search",       aphub: "/captured/ticker-analysis-live.html" },
  { id: "ap-dashboard",    label: "Dashboard",     group: "AlphaPod Live", icon: "layout-dashboard", aphub: "/captured/dashboard-live.html" },

  // Legacy — kept as-is
  { id: "trinity",    label: "Trinity",    group: "Legacy", legacy: true },
  { id: "heatseeker", label: "Heatseeker", group: "Legacy", legacy: true },
  { id: "skylit",     label: "Skylit",     group: "Legacy" },
  { id: "flowseeker", label: "Flowseeker", group: "Legacy" },
  { id: "portfolio",  label: "Portfolio",  group: "Legacy" },
  { id: "journal",    label: "Journal",    group: "Legacy" },
  { id: "swarmspx",   label: "SwarmSPX",   group: "Legacy" },
];

export const LEGACY_PAGES = new Set(NAV_ITEMS.filter(i => i.legacy).map(i => i.id));

// Map page id to display name for breadcrumb/header
export const PAGE_NAMES = {};
NAV_ITEMS.forEach(item => { PAGE_NAMES[item.id] = item.label; });

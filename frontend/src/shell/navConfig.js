export const SIDEBAR_KEY = "apw.sidebarCollapsed";

// legacy:true tabs render inside a .legacy-theme wrapper (preserved look)
// These are the pages we keep from the original floww project
// The original floww Meridian views — AlphaPod clone removed 2026-06-15.
export const NAV_ITEMS = [
  { id: "flowseeker-pro", label: "Screener", description: "Find unusual options activity", group: "Start here", icon: "activity", legacy: true },
  { id: "heatseeker", label: "Stock chart", description: "Study one stock and its price levels", group: "Study a stock", icon: "grid", legacy: true },
  { id: "trinity", label: "Market view", description: "Compare exposure and volatility", group: "Study a stock", icon: "layers", legacy: true },
  { id: "skylit", label: "Options map", description: "See exposure by strike and expiry", group: "Study a stock", icon: "bar-chart", legacy: true },
  { id: "steal-three", label: "Extra studies", description: "Compare option income and exposure", group: "Study a stock", icon: "sparkles", legacy: true },
  { id: "portfolio", label: "Portfolio", group: "Your records", icon: "trending-up" },
  { id: "journal", label: "Journal", group: "Your records", icon: "list" },
  { id: "public", label: "Broker", group: "Your records", icon: "briefcase" },
];

export const LEGACY_PAGES = new Set(NAV_ITEMS.filter(i => i.legacy).map(i => i.id));

// Map page id to display name for breadcrumb/header
export const PAGE_NAMES = {};
NAV_ITEMS.forEach(item => { PAGE_NAMES[item.id] = item.label; });

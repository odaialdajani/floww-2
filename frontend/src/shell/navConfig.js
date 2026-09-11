export const SIDEBAR_KEY = "apw.sidebarCollapsed";

// legacy:true tabs render inside a .legacy-theme wrapper (preserved look)
// These are the pages we keep from the original floww project
// The original floww Meridian views — AlphaPod clone removed 2026-06-15.
export const NAV_ITEMS = [
  // Decoder
  { id: "heatseeker", label: "Solstice", group: "Decoder", icon: "grid", legacy: true },
  { id: "trinity",    label: "Triad",    group: "Decoder", icon: "layers", legacy: true },
  { id: "skylit",     label: "Zenith",     group: "Decoder", icon: "bar-chart", legacy: true },
  // icon must be a key of ICONS in Sidebar.jsx — "zap" was not, so this item
  // silently rendered the default glyph.
  { id: "flowseeker-pro", label: "Tidehunter Pro", group: "Decoder", icon: "activity", legacy: true },
  // Steal Three was built (backend routes live, StealThreePreview rendered in
  // App.js) but had no nav entry and was excluded from the ?page= whitelist,
  // so it was unreachable.
  { id: "steal-three", label: "Steal Three", group: "Decoder", icon: "sparkles", legacy: true },

  // Trading
  { id: "portfolio",  label: "Portfolio",  group: "Trading", icon: "trending-up" },
  { id: "journal",    label: "Journal",    group: "Trading", icon: "list" },
  { id: "public",     label: "Broker",     group: "Trading", icon: "briefcase" },
];

export const LEGACY_PAGES = new Set(NAV_ITEMS.filter(i => i.legacy).map(i => i.id));

// Map page id to display name for breadcrumb/header
export const PAGE_NAMES = {};
NAV_ITEMS.forEach(item => { PAGE_NAMES[item.id] = item.label; });

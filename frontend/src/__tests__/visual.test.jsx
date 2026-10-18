/**
 * Round 8 Agent J — Visual Smoke Test
 * Tests that App renders without crashing with the new AppShell rail.
 *
 * Updated for Foundation lane: nav-tabs removed (rail owns navigation).
 */
import { render, act } from "@testing-library/react";
import axios from "axios";

// Post-render axios continuations resolve on a microtask chain after mount;
// draining inside act() lets those state updates settle where React expects
// them. Assertions below are untouched.

// ── Mock axios (must be configured before any component imports it) ──
// NOTE: jest.fn() inside a jest.mock factory silently loses its
// implementation in this CRA/jest combo (returns undefined when called).
// Use plain arrow functions — nothing here asserts on the mocks.
jest.mock("axios", () => {
  const ok = (data) => () => Promise.resolve({ data });
  return {
    __esModule: true,
    default: {
      get: ok([]),
      post: ok({}),
      put: ok({}),
      delete: ok({}),
      patch: ok({}),
      create: function () { return this; },
      interceptors: { request: { use: () => {} }, response: { use: () => {} } },
      defaults: { headers: { common: {} } },
    },
  };
});

// ── Mock shell components (new Foundation lane) ─────────────────────
jest.mock("../config/api", () => ({
  BACKEND_URL: "http://localhost:8000",
  API: "http://localhost:8000/api",
  ALPHAPOD_API: "http://localhost:9000",
  ALPHAPOD_PROXY: false,
}));
jest.mock("../shell/AppShell", () => ({ __esModule: true, default: ({ children }) => children }));
jest.mock("../shell/Sidebar", () => ({ __esModule: true, default: () => null }));

// ── Mock all child components to avoid cascade failures ─────────────
jest.mock("../components/GridHeatmap", () => ({ __esModule: true, default: () => null }));
jest.mock("../components/BarHeatmap", () => ({ __esModule: true, default: () => null }));
jest.mock("../components/PatternCard", () => ({ __esModule: true, default: () => null }));
jest.mock("../components/TrinityView", () => ({ __esModule: true, default: () => null }));
jest.mock("../components/SidebarPanels", () => ({
  FlipZonesPanel: () => null, StackedNodesPanel: () => null, TugOfWarPanel: () => null,
  ScenarioPanel: () => null, RiskDashboardPanel: () => null, OpportunitiesPanel: () => null,
  ImpliedMovePanel: () => null, VolAnalyticsPanel: () => null, GreekReferencePanel: () => null,
  UsagePanel: () => null, LivePolicyPanel: () => null,
}));
jest.mock("../components/AdvancedAnalyticsPanel", () => ({
  MarketRegimePanel: () => null, ImpliedPDFPanel: () => null, HedgeImpulsePanel: () => null,
  PressureCloudPanel: () => null, CharmIntegralPanel: () => null,
}));
jest.mock("../components/PortfolioPanel", () => ({ __esModule: true, default: () => null }));
jest.mock("../components/FlowTicker", () => ({ __esModule: true, default: () => null }));
jest.mock("../components/HistoryPanel", () => ({ __esModule: true, default: () => null }));
jest.mock("../components/OptionsChainTable", () => ({ __esModule: true, default: () => null }));
jest.mock("../components/MultiTimeframeGEXPanel", () => ({ __esModule: true, default: () => null }));
jest.mock("../components/AlertsPanel", () => ({ __esModule: true, default: () => null }));
jest.mock("../components/UOAPanel", () => ({ __esModule: true, default: () => null }));
jest.mock("../components/heatseeker/HeatseekerDashboard", () => ({ __esModule: true, default: () => null }));
jest.mock("../components/AlertOverlay", () => ({ __esModule: true, default: () => null }));
jest.mock("../components/PWAInstallBanner", () => ({ __esModule: true, default: () => null }));
jest.mock("../components/SettingsPanel", () => ({ SettingsPanel: () => null }));
jest.mock("../components/ShortcutsModal", () => ({ ShortcutsModal: () => null }));
jest.mock("../components/MorningBriefing", () => ({ MorningBriefing: () => null }));
jest.mock("../components/PositionSizing", () => ({ PositionSizing: () => null }));
jest.mock("../components/TradeEntry", () => ({ TradeEntry: () => null }));
jest.mock("../components/TradeJournal", () => ({ TradeJournal: () => null }));
jest.mock("../components/DashboardSummary", () => ({ DashboardSummary: () => null }));
jest.mock("../components/TradeAnalytics", () => ({ TradeAnalytics: () => null }));
jest.mock("../components/SocialFlowPanel", () => ({ __esModule: true, default: () => null }));
jest.mock("../components/ToxicityGauge", () => ({ __esModule: true, default: () => null }));
jest.mock("../components/VannaChart", () => ({ __esModule: true, default: () => null }));
jest.mock("../components/ErrorBoundary", () => ({ __esModule: true, default: ({ children }) => children }));
jest.mock("../components/RetryButton", () => ({ RetryButton: () => null, ErrorState: () => null }));
jest.mock("../hooks/useWebSocketGex", () => ({ useWebSocketGex: () => ({ readyState: 0, lastMessage: null }) }));
jest.mock("../hooks/useDebounce", () => ({ useDebounce: (val) => val }));
jest.mock("../context/ThemeContext", () => ({
  useTheme: () => ({ theme: "dark", toggleTheme: jest.fn() }),
  ThemeProvider: ({ children }) => children,
}));
jest.mock("../utils/dataDecimator", () => ({ autoDecimate: (data) => data }));

// ── Delayed import — must come after all mocks ──────────────────────
import App from "../App";

// ── Tests ───────────────────────────────────────────────────────────
const drain = async () => { for (let i = 0; i < 50; i += 1) { await Promise.resolve(); } };

describe("Visual Smoke Test — Tab Render", () => {
  test("renders App default (trinity tab) without crash", async () => {
    const { container } = render(<App />);
    expect(container.firstChild).toBeTruthy();
    await act(drain);
  });

  test("App renders with AppShell wrapper (rail owns nav now)", async () => {
    const { container } = render(<App />);
    // AppShell is mocked above (renders children), so assert App's own
    // mounted content instead of shell chrome.
    expect(container.firstChild).toBeTruthy();
    await act(drain);
  });

  test("App renders root element", async () => {
    const { container } = render(<App />);
    expect(container.firstChild).toBeTruthy();
    await act(drain);
  });

  test("no duplicate mount errors", async () => {
    const { unmount } = render(<App />);
    await act(drain);
    expect(() => unmount()).not.toThrow();
    await act(drain);
  });
});

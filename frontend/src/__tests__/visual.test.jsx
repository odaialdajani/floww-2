/**
 * Round 8 Agent J — Visual Smoke Test
 * Tests that App renders without crashing with the new AppShell rail.
 *
 * Updated for Foundation lane: nav-tabs removed (rail owns navigation).
 */
import { render } from "@testing-library/react";
import axios from "axios";

// ── Mock axios (must be configured before any component imports it) ──
jest.mock("axios", () => {
  const mockAxios = {
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
    patch: jest.fn(),
    create: jest.fn(() => mockAxios),
    interceptors: { request: { use: jest.fn() }, response: { use: jest.fn() } },
    defaults: { headers: { common: {} } },
  };
  return { __esModule: true, default: mockAxios };
});

// CRA's Jest preset sets `resetMocks: true`, which clears every jest.fn()
// implementation (back to returning `undefined`) before each test. App.js calls
// `axios.get(...).then(...)` synchronously inside a mount useEffect, so the mock
// must resolve to a Promise or the render throws. Re-install resolved defaults
// here so the implementations survive the per-test reset.
beforeEach(() => {
  axios.get.mockResolvedValue({ data: [] });
  axios.post.mockResolvedValue({ data: {} });
  axios.put.mockResolvedValue({ data: {} });
  axios.delete.mockResolvedValue({ data: {} });
  axios.patch.mockResolvedValue({ data: {} });
  axios.create.mockReturnValue(axios);
});

// ── Mock auth so App renders its authenticated AppShell-wrapped chrome ──
// App.js short-circuits to a login screen when `!isAuthenticated`; the rail +
// header (.ap-header) only mount past that gate. Mock an authenticated session
// so the smoke test exercises the real app shell, not the login page.
jest.mock("../context/AuthContext", () => ({
  __esModule: true,
  useAuth: () => ({
    token: "test-token",
    user: { email: "test@example.com", tier: "pro" },
    tier: "pro",
    isAuthenticated: true,
    login: jest.fn(),
    logout: jest.fn(),
  }),
  AuthProvider: ({ children }) => children,
  authHeaders: () => ({}),
}));

// ── Mock shell components (new Foundation lane) ─────────────────────
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
describe("Visual Smoke Test — Tab Render", () => {
  test("renders App default (trinity tab) without crash", () => {
    const { container } = render(<App />);
    expect(container.firstChild).toBeTruthy();
  });

  test("App renders with AppShell wrapper (rail owns nav now)", () => {
    const { container } = render(<App />);
    // The Foundation-lane refactor dropped the legacy `.App` root class; the
    // persistent app chrome is now <header class="ap-header">, rendered
    // unconditionally inside the AppShell wrapper. Assert that mounts.
    expect(container.querySelector(".ap-header")).toBeTruthy();
  });

  test("App renders root element", () => {
    const { container } = render(<App />);
    expect(container.firstChild).toBeTruthy();
  });

  test("no duplicate mount errors", () => {
    const { unmount } = render(<App />);
    expect(() => unmount()).not.toThrow();
  });
});

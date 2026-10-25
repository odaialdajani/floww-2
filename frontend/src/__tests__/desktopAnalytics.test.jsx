import React from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import fs from "fs";
import path from "path";

// Desktop composition contracts for the Stock page:
// 1. The visible Analytics affordance must reach the REAL existing analysis
//    destination (the analytical range workspace) — not dead sidebar state.
// 2. The dashboard scroll container disables browser scroll anchoring so a
//    late-mounting candle chart cannot nudge the container's scroll position
//    (bounded mitigation for the observed, non-deterministic initial-scroll
//    symptom; user scrolling is untouched by the rule).

jest.mock("axios", () => {
  const ok = (data) => () => Promise.resolve({ data });
  return {
    __esModule: true,
    default: {
      get: ok([]), post: ok({}), put: ok({}), delete: ok({}), patch: ok({}),
      create: function () { return this; },
      interceptors: { request: { use: () => {} }, response: { use: () => {} } },
      defaults: { headers: { common: {} } },
    },
  };
});
jest.mock("../config/api", () => ({ BACKEND_URL: "http://localhost:8000", API: "http://localhost:8000/api", ALPHAPOD_API: "http://localhost:9000", ALPHAPOD_PROXY: false }));
jest.mock("../shell/AppShell", () => ({ __esModule: true, default: ({ children }) => children }));
jest.mock("../shell/Sidebar", () => ({ __esModule: true, default: () => null }));
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

import App from "../App";

const drain = async () => { for (let i = 0; i < 60; i += 1) { await Promise.resolve(); } };

beforeEach(() => {
  window.history.replaceState({}, "", "/?page=heatseeker");
  try { window.localStorage.clear(); } catch { /* noop */ }
});

test("the visible Analytics affordance opens the real analytical range workspace", async () => {
  const { container } = render(<App />);
  await act(drain);
  expect(container.firstChild).toBeTruthy();
  const analytics = screen.getByRole("button", { name: /Analytics/ });
  expect(screen.queryByTestId("analytical-range-card")).not.toBeInTheDocument();
  fireEvent.click(analytics);
  await act(drain);
  expect(screen.getByTestId("analytical-range-card")).toBeInTheDocument();
  // toggling back closes the workspace — the control is a real two-state action
  fireEvent.click(analytics);
  await act(drain);
  expect(screen.queryByTestId("analytical-range-card")).not.toBeInTheDocument();
});

test("the study/chart toolbar carries a reachable Analytical range toggle at desktop", async () => {
  const { container } = render(<App />);
  await act(drain);
  expect(container.firstChild).toBeTruthy();
  const toggle = screen.getByTestId("analytical-range-toggle");
  expect(toggle).toHaveAttribute("aria-pressed", "false");
  expect(screen.queryByTestId("analytical-range-card")).not.toBeInTheDocument();
  fireEvent.click(toggle);
  await act(drain);
  expect(screen.getByTestId("analytical-range-card")).toBeInTheDocument();
  // the toolbar path can remount the actions when the study area switches —
  // always re-query the live node instead of holding a stale reference
  expect(screen.getByTestId("analytical-range-toggle")).toHaveAttribute("aria-pressed", "true");
  fireEvent.click(screen.getByTestId("analytical-range-toggle"));
  await act(drain);
  expect(screen.queryByTestId("analytical-range-card")).not.toBeInTheDocument();
  expect(screen.getByTestId("analytical-range-toggle")).toHaveAttribute("aria-pressed", "false");
});

test("the dashboard scroll container disables browser scroll anchoring", () => {
  const css = fs.readFileSync(path.resolve(__dirname, "../App.css"), "utf8");
  const block = css.slice(css.indexOf(".skylit-full-dashboard {"));
  expect(block.slice(0, block.indexOf("}") + 1)).toContain("overflow-anchor: none");
});

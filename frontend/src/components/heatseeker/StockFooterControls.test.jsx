import React from "react";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import "@testing-library/jest-dom";
import fs from "fs";
import path from "path";

// Stock footer / floating-control lane contracts (S02):
// 1. The Stock footer's Analytics/open-range control must stay clear of the
//    floating App health / Ask Flow controls, and the two floating controls
//    must never cover each other.
// 2. Each of those controls stays individually reachable by keyboard.
// jsdom has no layout engine, so the geometry is pinned by a CSS contract on
// NeutralTheme.css and the reachability is mounted. Real Chrome and
// native200 acceptance stay with Root.

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
jest.mock("../../config/api", () => ({ BACKEND_URL: "http://localhost:8000", API: "http://localhost:8000/api", ALPHAPOD_API: "http://localhost:9000", ALPHAPOD_PROXY: false }));
jest.mock("../../shell/Sidebar", () => ({ __esModule: true, default: () => null }));
jest.mock("../../components/GridHeatmap", () => ({ __esModule: true, default: () => null }));
jest.mock("../../components/BarHeatmap", () => ({ __esModule: true, default: () => null }));
jest.mock("../../components/PatternCard", () => ({ __esModule: true, default: () => null }));
jest.mock("../../components/TrinityView", () => ({ __esModule: true, default: () => null }));
jest.mock("../../components/SidebarPanels", () => ({
  FlipZonesPanel: () => null, StackedNodesPanel: () => null, TugOfWarPanel: () => null,
  ScenarioPanel: () => null, RiskDashboardPanel: () => null, OpportunitiesPanel: () => null,
  ImpliedMovePanel: () => null, VolAnalyticsPanel: () => null, GreekReferencePanel: () => null,
  UsagePanel: () => null, LivePolicyPanel: () => null,
}));
jest.mock("../../components/AdvancedAnalyticsPanel", () => ({
  MarketRegimePanel: () => null, ImpliedPDFPanel: () => null, HedgeImpulsePanel: () => null,
  PressureCloudPanel: () => null, CharmIntegralPanel: () => null,
}));
jest.mock("../../components/PortfolioPanel", () => ({ __esModule: true, default: () => null }));
jest.mock("../../components/FlowTicker", () => ({ __esModule: true, default: () => null }));
jest.mock("../../components/HistoryPanel", () => ({ __esModule: true, default: () => null }));
jest.mock("../../components/OptionsChainTable", () => ({ __esModule: true, default: () => null }));
jest.mock("../../components/MultiTimeframeGEXPanel", () => ({ __esModule: true, default: () => null }));
jest.mock("../../components/AlertsPanel", () => ({ __esModule: true, default: () => null }));
jest.mock("../../components/UOAPanel", () => ({ __esModule: true, default: () => null }));
jest.mock("../../components/heatseeker/HeatseekerDashboard", () => ({ __esModule: true, default: () => null }));
jest.mock("../../components/AlertOverlay", () => ({ __esModule: true, default: () => null }));
jest.mock("../../components/PWAInstallBanner", () => ({ __esModule: true, default: () => null }));
jest.mock("../../components/SettingsPanel", () => ({ SettingsPanel: () => null }));
jest.mock("../../components/ShortcutsModal", () => ({ ShortcutsModal: () => null }));
jest.mock("../../components/MorningBriefing", () => ({ MorningBriefing: () => null }));
jest.mock("../../components/PositionSizing", () => ({ PositionSizing: () => null }));
jest.mock("../../components/TradeEntry", () => ({ TradeEntry: () => null }));
jest.mock("../../components/TradeJournal", () => ({ TradeJournal: () => null }));
jest.mock("../../components/DashboardSummary", () => ({ DashboardSummary: () => null }));
jest.mock("../../components/TradeAnalytics", () => ({ TradeAnalytics: () => null }));
jest.mock("../../components/SocialFlowPanel", () => ({ __esModule: true, default: () => null }));
jest.mock("../../components/ToxicityGauge", () => ({ __esModule: true, default: () => null }));
jest.mock("../../components/VannaChart", () => ({ __esModule: true, default: () => null }));
jest.mock("../../components/ErrorBoundary", () => ({ __esModule: true, default: ({ children }) => children }));
jest.mock("../../components/RetryButton", () => ({ RetryButton: () => null, ErrorState: () => null }));
jest.mock("../../hooks/useWebSocketGex", () => ({ useWebSocketGex: () => ({ readyState: 0, lastMessage: null }) }));
jest.mock("../../hooks/useDebounce", () => ({ useDebounce: (val) => val }));
jest.mock("../../context/ThemeContext", () => ({
  useTheme: () => ({ theme: "dark", toggleTheme: jest.fn() }),
  ThemeProvider: ({ children }) => children,
}));
jest.mock("../../utils/dataDecimator", () => ({ autoDecimate: (data) => data }));

import App from "../../App";

const drain = async () => { for (let i = 0; i < 60; i += 1) { await Promise.resolve(); } };
const neutralThemeCss = () => fs.readFileSync(path.resolve(__dirname, "../../NeutralTheme.css"), "utf8");

beforeEach(() => {
  window.history.replaceState({}, "", "/?page=heatseeker");
  try { window.localStorage.clear(); } catch { /* noop */ }
});

test("the Stock footer reserves the floating-control lane instead of running under the Ask Flow opener", () => {
  const css = neutralThemeCss();
  expect(css).toMatch(/@media screen and \(min-width:\s*1024px\)/);
  expect(css).toMatch(/body:has\(\.heatseeker-layout\)\s+\.mobile-toggle-bar\s*\{[^}]*padding-right:\s*140px/);
  expect(css).toMatch(/body:has\(\.heatseeker-layout\)\s+\.floww-page-footer\s*\{[^}]*padding-right:\s*140px/);
});

test("the App health chip is kept clear of the Ask Flow opener on narrow screens", () => {
  const css = neutralThemeCss();
  expect(css).toMatch(/@media screen and \(max-width:\s*768px\)/);
  expect(css).toMatch(/aside\[aria-label="App health"\]\s*\{[^}]*bottom:\s*calc\(116px \+ env\(safe-area-inset-bottom\)\)\s*!important/);
});

test("the App health chip carries a neutral control surface instead of stray text", () => {
  const css = neutralThemeCss();
  expect(css).toMatch(/aside\[aria-label="App health"\] > button\s*\{[^}]*background:\s*var\(--floww-raised\)/);
  expect(css).toMatch(/aside\[aria-label="App health"\] > button\s*\{[^}]*border:\s*1px solid var\(--floww-line\)/);
});

test("the Stock footer control and both floating controls stay individually reachable", async () => {
  const { container } = render(<App />);
  await act(drain);
  const strip = container.querySelector(".mobile-toggle-bar");
  expect(strip).toBeTruthy();
  const analytics = within(strip).getByRole("button", { name: /Analytics/ });
  const askFlow = screen.getByRole("button", { name: "Open Ask Flow" });
  const health = screen.getByRole("button", { name: "App health" });
  for (const control of [analytics, askFlow, health]) {
    expect(control).not.toBeDisabled();
    expect(control).not.toHaveAttribute("aria-hidden", "true");
    control.focus();
    expect(document.activeElement).toBe(control);
  }
  expect(askFlow.contains(health)).toBe(false);
  expect(strip.contains(askFlow)).toBe(false);
  expect(strip.contains(health)).toBe(false);
});

test("the Stock footer open-range control still reaches the real analytical range workspace", async () => {
  const { container } = render(<App />);
  await act(drain);
  const strip = container.querySelector(".mobile-toggle-bar");
  const analytics = within(strip).getByRole("button", { name: /Analytics/ });
  expect(screen.queryByTestId("analytical-range-card")).not.toBeInTheDocument();
  fireEvent.click(analytics);
  await act(drain);
  expect(screen.getByTestId("analytical-range-card")).toBeInTheDocument();
});

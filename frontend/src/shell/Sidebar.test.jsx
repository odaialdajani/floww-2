/**
 * @jest-environment jsdom
 */
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import Sidebar from "./Sidebar";
import { SIDEBAR_KEY, NAV_ITEMS } from "./navConfig";
import fs from "fs";
import path from "path";

beforeEach(() => localStorage.clear());

test("renders nav items and reflects active page", () => {
  render(<Sidebar page="trinity" onNavigate={() => {}} />);
  // Pin to current NAV_ITEMS (Flow Alerts left the config long ago; the
  // Stock chart entry is the stable first Decoder item).
  expect(screen.getByRole("button", { name: /Stock chart/ })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Market view/ })).toHaveAttribute("aria-current", "page");
});

test("clicking a nav item calls onNavigate with its id", () => {
  const onNavigate = jest.fn();
  render(<Sidebar page="trinity" onNavigate={onNavigate} />);
  fireEvent.click(screen.getByRole("button", { name: /Stock chart/ }));
  expect(onNavigate).toHaveBeenCalledWith("heatseeker");
});

test("collapse toggle persists to localStorage apw.sidebarCollapsed", () => {
  render(<Sidebar page="trinity" onNavigate={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: /collapse sidebar/i }));
  expect(localStorage.getItem(SIDEBAR_KEY)).toBe("true");
  expect(screen.getByRole("button",{name:"Stock chart",exact:true})).toBeInTheDocument();
  expect(screen.getByRole("button",{name:"Screener",exact:true})).toBeInTheDocument();
});

// Extra studies shipped with backend routes and a rendered component but no nav
// entry and no ?page= whitelist slot, so it was unreachable in the UI.
test("Extra studies is reachable from the sidebar", () => {
  const onNavigate = jest.fn();
  render(<Sidebar page="trinity" onNavigate={onNavigate} />);
  fireEvent.click(screen.getByRole("button", { name: /Extra studies/ }));
  expect(onNavigate).toHaveBeenCalledWith("steal-three");
});

// "zap" was set on Screener but is not a key of ICONS, so that item
// silently fell back to the default glyph. Pin every icon to a real key.
test("every nav icon exists in the Sidebar ICONS map", () => {
  const src = fs.readFileSync(path.join(__dirname, "Sidebar.jsx"), "utf8");
  const block = src.slice(src.indexOf("const ICONS"), src.indexOf("function getIcon"));
  const known = new Set([...block.matchAll(/^\s{2}"?([a-z0-9-]+)"?:/gm)].map((m) => m[1]));
  const missing = NAV_ITEMS.filter((i) => !known.has(i.icon)).map((i) => `${i.label} -> ${i.icon}`);
  expect(missing).toEqual([]);
});

// Runtime deep-link/refresh behavior for every NAV_ITEMS id lives in the hook suite.
test("App mounts the registry-backed browser navigation hook", () => {
  const app = fs.readFileSync(path.join(__dirname, "..", "App.js"), "utf8");
  expect(app).toContain('import useWorkspaceNavigation from "./shell/useWorkspaceNavigation"');
  expect(app).toContain('const [page, setPage, navigation] = useWorkspaceNavigation();');
});

test("records start folded and their toggle opens and closes them", () => {
  render(<Sidebar page="flowseeker-pro" onNavigate={() => {}} />);
  const toggle=screen.getByRole("button",{name:"Your records",exact:true});
  expect(toggle).toHaveAttribute("aria-expanded","false");
  expect(screen.queryByRole("button",{name:"Portfolio",exact:true})).toBeNull();
  fireEvent.click(toggle);
  expect(screen.getByRole("button",{name:"Portfolio",exact:true})).toBeInTheDocument();
  fireEvent.click(toggle);
  expect(screen.queryByRole("button",{name:"Journal",exact:true})).toBeNull();
});

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
  // Solstice entry is the stable first Decoder item).
  expect(screen.getByRole("button", { name: /Solstice/ })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Triad/ })).toHaveAttribute("aria-current", "page");
});

test("clicking a nav item calls onNavigate with its id", () => {
  const onNavigate = jest.fn();
  render(<Sidebar page="trinity" onNavigate={onNavigate} />);
  fireEvent.click(screen.getByRole("button", { name: /Solstice/ }));
  expect(onNavigate).toHaveBeenCalledWith("heatseeker");
});

test("collapse toggle persists to localStorage apw.sidebarCollapsed", () => {
  render(<Sidebar page="trinity" onNavigate={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: /collapse sidebar/i }));
  expect(localStorage.getItem(SIDEBAR_KEY)).toBe("true");
  expect(screen.getByRole("button",{name:"Solstice",exact:true})).toBeInTheDocument();
  expect(screen.getByRole("button",{name:"Tidehunter Pro",exact:true})).toBeInTheDocument();
});

// Steal Three shipped with backend routes and a rendered component but no nav
// entry and no ?page= whitelist slot, so it was unreachable in the UI.
test("Steal Three is reachable from the sidebar", () => {
  const onNavigate = jest.fn();
  render(<Sidebar page="trinity" onNavigate={onNavigate} />);
  fireEvent.click(screen.getByRole("button", { name: /Steal Three/ }));
  expect(onNavigate).toHaveBeenCalledWith("steal-three");
});

// "zap" was set on Tidehunter Pro but is not a key of ICONS, so that item
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
  expect(app).toContain('const [page, setPage] = useWorkspaceNavigation();');
});

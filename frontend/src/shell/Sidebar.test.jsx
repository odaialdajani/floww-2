import { render, screen, fireEvent } from "@testing-library/react";
import Sidebar from "./Sidebar";
import { SIDEBAR_KEY } from "./navConfig";

beforeEach(() => localStorage.clear());

test("renders nav items and reflects active page", () => {
  render(<Sidebar page="trinity" onNavigate={() => {}} />);
  expect(screen.getByRole("button", { name: "Flow Alerts" })).toBeInTheDocument();
  // Legacy group is collapsed by default — expand it to reach the active Trinity item.
  fireEvent.click(screen.getByRole("button", { name: /Legacy/i }));
  expect(screen.getByRole("button", { name: /Trinity/ })).toHaveAttribute("aria-current", "page");
});

test("clicking a nav item calls onNavigate with its id", () => {
  const onNavigate = jest.fn();
  render(<Sidebar page="trinity" onNavigate={onNavigate} />);
  fireEvent.click(screen.getByRole("button", { name: "Flow Alerts" }));
  expect(onNavigate).toHaveBeenCalledWith("flow-alerts");
});

test("collapse toggle persists to localStorage apw.sidebarCollapsed", () => {
  render(<Sidebar page="trinity" onNavigate={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: /collapse sidebar/i }));
  expect(localStorage.getItem(SIDEBAR_KEY)).toBe("true");
});

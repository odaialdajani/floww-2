import React from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { SettingsPanel } from "./SettingsPanel";

beforeEach(() => localStorage.clear());

function openSettings() {
  render(<SettingsPanel refreshMs={25000} defaultTicker="SPY" />);
  fireEvent.click(screen.getByRole("button", { name: /^Settings/ }));
}

test("general setting saves preserve the child's latest saved layout and screens", () => {
  const custom = { id: "mine", custom: true, conditions: [], ruleUnitsVersion: 2 };
  localStorage.setItem("floww_settings", JSON.stringify({ tidehunter: { screens: [custom] } }));
  openSettings();
  fireEvent.click(screen.getByRole("button", { name: "monitor" }));
  fireEvent.click(screen.getByRole("button", { name: "10s" }));
  const saved = JSON.parse(localStorage.getItem("floww_settings"));
  expect(saved.tidehunter.mode).toBe("monitor");
  expect(saved.tidehunter.screens).toEqual([custom]);
  expect(saved.refreshMs).toBe(10000);
});

test("general accessibility reflects another window and preserves its other preferences", () => {
  openSettings();
  act(() => {
    localStorage.setItem("floww_settings", JSON.stringify({ colorBlindMode: true, tidehunter: { mode: "research" }, other: "keep" }));
    window.dispatchEvent(new StorageEvent("storage", { key: "floww_settings" }));
  });
  fireEvent.click(screen.getByRole("button", { name: "Disable color-blind mode" }));
  expect(screen.getByRole("button", { name: "Enable color-blind mode" })).toBeInTheDocument();
  expect(JSON.parse(localStorage.getItem("floww_settings"))).toMatchObject({ colorBlindMode: false, tidehunter: { mode: "research" }, other: "keep" });
});

test("failed general save is visible and does not report the new value as saved", () => {
  openSettings();
  const fail = jest.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("full"); });
  fireEvent.click(screen.getByRole("button", { name: "10s" }));
  expect(screen.getByRole("alert")).toHaveTextContent(/could not be saved/i);
  fail.mockRestore();
});

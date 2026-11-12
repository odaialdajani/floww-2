/** @jest-environment jsdom */
import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import AskFlow from "./AskFlow";
import AgentProvider from "../../agent/AgentProvider";
import { publishScreenContext } from "../../agent/useScreenContext";

const liveContext = () => publishScreenContext({
  ticker: "SPY", page: "heatseeker", overlayMetric: "raw", displayMode: "live",
});

const openMenu = () => {
  fireEvent.click(screen.getByTestId("ask-lodestar-btn"));
  return screen.getAllByRole("menuitem");
};

test("an open Ask Flow menu owns its keys: a letter or digit never reaches the window shortcut handler", () => {
  liveContext();
  const seen = [];
  const listener = event => seen.push(event.key);
  window.addEventListener("keydown", listener);
  try {
    render(<AgentProvider><AskFlow /></AgentProvider>);
    const items = openMenu();
    expect(items[0]).toHaveFocus();
    fireEvent.keyDown(items[0], { key: "d" });
    fireEvent.keyDown(items[0], { key: "2" });
    fireEvent.keyDown(items[0], { key: "v" });
    expect(seen).toEqual([]);
  } finally {
    window.removeEventListener("keydown", listener);
  }
});

test("the Ask Flow trigger opens the menu with ArrowUp and never leaks the ticker-cycle key", () => {
  liveContext();
  const seen = [];
  const listener = event => seen.push(event.key);
  window.addEventListener("keydown", listener);
  try {
    render(<AgentProvider><AskFlow /></AgentProvider>);
    const trigger = screen.getByTestId("ask-lodestar-btn");
    trigger.focus();
    fireEvent.keyDown(trigger, { key: "ArrowUp" });
    const items = screen.getAllByRole("menuitem");
    expect(items.length).toBeGreaterThan(0);
    expect(items[items.length - 1]).toHaveFocus();
    expect(seen).toEqual([]);
  } finally {
    window.removeEventListener("keydown", listener);
  }
});

test("menu arrows and Escape keep their own behaviour and stay out of the window handler", () => {
  liveContext();
  const seen = [];
  const listener = event => seen.push(event.key);
  window.addEventListener("keydown", listener);
  try {
    render(<AgentProvider><AskFlow /></AgentProvider>);
    const trigger = screen.getByTestId("ask-lodestar-btn");
    const items = openMenu();
    fireEvent.keyDown(items[0], { key: "ArrowDown" });
    expect(items[1]).toHaveFocus();
    fireEvent.keyDown(items[1], { key: "ArrowUp" });
    expect(items[0]).toHaveFocus();
    fireEvent.keyDown(items[0], { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    expect(trigger).toHaveFocus();
    expect(seen).toEqual([]);
  } finally {
    window.removeEventListener("keydown", listener);
  }
});

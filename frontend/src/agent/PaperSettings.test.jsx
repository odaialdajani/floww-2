import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import PaperSettings, { PAPER_SETUP_KEY } from "./PaperSettings";

beforeEach(() => localStorage.clear());

test.each([
  { slippageEnabled: "on", slippageMethod: "both" },
  { slippageEnabled: "enabled", slippageMethod: "cash" },
  { slippageEnabled: true, slippageMethod: false, name: { invalid: true } },
])("malformed saved choices are cleared without picking defaults: %j", values => {
  localStorage.setItem(PAPER_SETUP_KEY, JSON.stringify({ version: 1, accountChoice: "new", selectedAccount: "",
    drafts: { new: values, "account:other": { slippageEnabled: "bad", slippageMethod: "both" } } }));
  render(<PaperSettings />);
  fireEvent.click(screen.getByText("Save paper setup"));
  const saved = JSON.parse(localStorage.getItem(PAPER_SETUP_KEY));
  for (const draft of Object.values(saved.drafts)) {
    expect(["", "on", "off"]).toContain(draft.slippageEnabled);
    expect(["", "price", "cash"]).toContain(draft.slippageMethod);
    expect(typeof draft.name).toBe("string");
  }
});

test.each(["", " "])("empty account identity cannot count as selection: %j", id => {
  render(<PaperSettings accounts={[{ id, name: "Malformed", paper: true, venue: "internal" }]} />);
  fireEvent.change(screen.getByLabelText("Paper account"), { target: { value: "existing" } });
  fireEvent.click(screen.getByText("Save paper setup"));
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  expect(screen.getByRole("alert")).toHaveTextContent("Choose a paper account");
});

test("both methods and on/off save without changing earlier fills or opening trades", () => {
  const { unmount } = render(<PaperSettings />);
  fireEvent.change(screen.getByLabelText("Paper account"), { target: { value: "new" } });
  fireEvent.change(screen.getByLabelText("Slippage"), { target: { value: "on" } });
  fireEvent.change(screen.getByLabelText("How slippage is charged"), { target: { value: "price" } });
  fireEvent.change(screen.getByLabelText("Price difference ($)"), { target: { value: "0.05" } });
  fireEvent.click(screen.getByText("Save paper setup"));
  expect(JSON.parse(localStorage.getItem(PAPER_SETUP_KEY)).drafts.new.slippageMethod).toBe("price");
  fireEvent.change(screen.getByLabelText("How slippage is charged"), { target: { value: "cash" } });
  fireEvent.change(screen.getByLabelText("Slippage"), { target: { value: "off" } });
  fireEvent.click(screen.getByText("Save paper setup"));
  expect(screen.getByRole("status")).toHaveTextContent("does not open an account or place a trade");
  unmount(); render(<PaperSettings />);
  expect(screen.getByLabelText("Slippage")).toHaveValue("off");
  expect(screen.getByLabelText("How slippage is charged")).toHaveValue("cash");
  expect(screen.getByLabelText("Starting cash ($)")).toHaveValue("");
});

test("selected accounts retain separate choices and live accounts are excluded", () => {
  render(<PaperSettings accounts={[
    { id: "one", name: "Practice one", venue: "internal", paper: true },
    { id: "two", name: "Practice two", venue: "internal", paper: true },
    { id: "live", name: "Live money", venue: "internal", paper: false },
  ]} />);
  fireEvent.change(screen.getByLabelText("Paper account"), { target: { value: "existing" } });
  expect(screen.queryByText("Live money")).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Saved paper account"), { target: { value: "one" } });
  fireEvent.change(screen.getByLabelText("Slippage"), { target: { value: "on" } });
  fireEvent.change(screen.getByLabelText("How slippage is charged"), { target: { value: "cash" } });
  fireEvent.change(screen.getByLabelText("Saved paper account"), { target: { value: "two" } });
  expect(screen.getByLabelText("Slippage")).toHaveValue("");
  fireEvent.change(screen.getByLabelText("Slippage"), { target: { value: "off" } });
  fireEvent.change(screen.getByLabelText("Saved paper account"), { target: { value: "one" } });
  expect(screen.getByLabelText("Slippage")).toHaveValue("on");
  expect(screen.getByLabelText("How slippage is charged")).toHaveValue("cash");
});

test("unavailable accounts and invalid money never claim a successful save", () => {
  render(<PaperSettings />);
  fireEvent.change(screen.getByLabelText("Paper account"), { target: { value: "existing" } });
  expect(screen.getByLabelText("Saved paper account")).toBeDisabled();
  fireEvent.click(screen.getByText("Save paper setup"));
  expect(screen.getByRole("alert")).toHaveTextContent("Choose a paper account");
  fireEvent.change(screen.getByLabelText("Paper account"), { target: { value: "new" } });
  fireEvent.change(screen.getByLabelText("Starting cash ($)"), { target: { value: "-10" } });
  fireEvent.click(screen.getByText("Save paper setup"));
  expect(screen.getByRole("alert")).toHaveTextContent("positive dollar amount");
  expect(localStorage.getItem(PAPER_SETUP_KEY)).toBeNull();
});

test("failed browser storage does not claim settings were saved", () => {
  render(<PaperSettings />);
  fireEvent.change(screen.getByLabelText("Paper account"), { target: { value: "new" } });
  const write = jest.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("full"); });
  fireEvent.click(screen.getByText("Save paper setup"));
  expect(screen.getByRole("alert")).toHaveTextContent("could not be saved");
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  write.mockRestore();
});

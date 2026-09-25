import { fireEvent, render, screen, act } from "@testing-library/react";
import axios from "axios";
import Movers from "./Movers";

jest.mock("axios");

const V2 = {
  schema_version: "movers.v2", mode: "previous_completed_session", status: "ok",
  session_date: "2026-09-24", prior_session_date: "2026-09-23",
  universe_id: "tracked-options.v1",
  coverage: { requested: 75, valid: 70, excluded: 5 },
  results: [
    { ticker: "MSFT", change_pct: -9.0000000001, close: 400, previous_close: 440, status: "ok", pct: -9.0000000001, change: -9.0000000001 },
    { ticker: "AAPL", change_pct: 4.2, close: 210, previous_close: 201.5, status: "ok", pct: 4.2, change: 4.2 },
  ],
};

describe("Movers (R7-01)", () => {
  beforeEach(() => { jest.clearAllMocks(); jest.useFakeTimers(); });
  afterEach(() => { jest.useRealTimers(); });

  test("renders ranked rows, one onPick per click/Enter", async () => {
    axios.get.mockResolvedValue({ data: V2 });
    const onPick = jest.fn();
    await act(async () => { render(<Movers onPick={onPick} />); });
    const rows = screen.getAllByTestId(/movers-row-/);
    expect(rows.map((r) => r.getAttribute("data-testid"))).toEqual(
      ["movers-row-MSFT", "movers-row-AAPL"]);
    expect(screen.getByTestId("movers-meta").textContent).toContain("2026-09-24");
    await act(async () => { fireEvent.click(screen.getByTestId("movers-row-AAPL")); });
    expect(onPick).toHaveBeenCalledTimes(1);
    expect(onPick).toHaveBeenCalledWith("AAPL");
    await act(async () => { fireEvent.keyDown(screen.getByTestId("movers-row-MSFT"), { key: "Enter" }); });
    expect(onPick).toHaveBeenCalledTimes(2);
    expect(onPick).toHaveBeenLastCalledWith("MSFT");
  });

  test("empty results show empty state, errors show retry", async () => {
    axios.get.mockResolvedValue({ data: { ...V2, status: "ok", results: [] } });
    const { unmount } = await act(async () => { const r = render(<Movers onPick={() => {}} />); return r; });
    expect(screen.queryByTestId("movers-retry")).toBeNull();
    expect(screen.getByText("No eligible rows")).toBeInTheDocument();
    unmount();
    axios.get.mockResolvedValue({ data: { ...V2, status: "unavailable", results: [] } });
    await act(async () => { render(<Movers onPick={() => {}} />); });
    expect(screen.getByTestId("movers-retry")).toBeInTheDocument();
  });

  test("provider failure shows retry; retry refetches", async () => {
    axios.get.mockRejectedValueOnce(new Error("down"));
    const onPick = jest.fn();
    await act(async () => { render(<Movers onPick={onPick} />); });
    expect(screen.getByTestId("movers-retry")).toBeInTheDocument();
    axios.get.mockResolvedValueOnce({ data: V2 });
    await act(async () => { fireEvent.click(screen.getByTestId("movers-retry")); });
    expect(screen.getByTestId("movers-row-AAPL")).toBeInTheDocument();
  });

  test("stale payload keeps rows with a last-good badge", async () => {
    axios.get.mockResolvedValue({ data: { ...V2, status: "stale" } });
    await act(async () => { render(<Movers onPick={() => {}} />); });
    expect(screen.getByTestId("movers-row-MSFT")).toBeInTheDocument();
    expect(screen.getByTestId("movers-stale")).toBeInTheDocument();
  });
});

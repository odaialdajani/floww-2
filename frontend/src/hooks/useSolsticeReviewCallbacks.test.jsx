import { renderHook } from "@testing-library/react";
import useSolsticeReviewCallbacks from "./useSolsticeReviewCallbacks";
import fs from "fs";
import path from "path";

test("mounted Solstice call sites use stable callbacks and no legacy guessed-contract fetch", () => {
  const app = fs.readFileSync(path.join(__dirname, "../App.js"), "utf8");
  expect((app.match(/onCellClick=\{solsticeCallbacks.cell\}/g) || []).length).toBe(2);
  expect((app.match(/onRefresh=\{solsticeCallbacks.reload\}/g) || []).length).toBe(2);
  expect(app).not.toContain("`${API}/contract/${ticker}/${strike}/${colKey}`");
});

test("spot polling retains callback identity but events read the latest symbol/snapshot; unknown OI stays null", () => {
  const onReview = jest.fn(), setMode = jest.fn(), refresh = jest.fn(), clearError = jest.fn();
  const props = { ticker: "SPY", spot: 100, data: { snapshotId: "a", strikes: [{ strike: 100 }] }, onReview, setMode, refresh, clearError };
  const { result, rerender } = renderHook(p => useSolsticeReviewCallbacks(p), { initialProps: props });
  const callbacks = result.current;
  rerender({ ...props, ticker: "QQQ", spot: 101, data: { snapshotId: "b", strikes: [{ strike: 100 }], grid: { grid: { "2031-01-17": { 100: 100000 } } } } });
  expect(result.current.cell).toBe(callbacks.cell);
  expect(result.current.strike).toBe(callbacks.strike);
  expect(result.current.reload).toBe(callbacks.reload);
  result.current.cell(100, "2031-01-17", 5000, { metric: "session_delta_volume", view: "gex" });
  expect(onReview).toHaveBeenCalledWith(expect.objectContaining({ ticker: "QQQ", snapshotId: "b", spot: 101, gex: 100000, selectedValue: 5000, oi: null, delta: null, oi_symbol: null }));
});

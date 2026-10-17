import React from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import BriefingStrip from "./BriefingStrip";

// Synthetic fixtures only; neither fetch nor clipboard reaches a real adapter.
const spy = { ticker: "SPY", asof: "2026-10-16T14:00:00Z", regime: "SPY_OLD", metrics: { net_gex: 123456789 } };
const qqq = { ticker: "QQQ", asof: "2026-10-16T14:01:00Z", regime: "QQQ_CURRENT", metrics: { net_gex: -987654321 } };
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};
const response = data => ({ ok: true, json: async () => data });
const originalFetch = global.fetch;
const originalClipboard = Object.getOwnPropertyDescriptor(navigator, "clipboard");
let requests, writeText;
beforeEach(() => {
  requests = [];
  global.fetch = jest.fn((url, options) => {
    const request = { ...deferred(), url, signal: options.signal };
    requests.push(request);
    return request.promise; // Intentionally ignores abort, like a slow adapter.
  });
  writeText = jest.fn(async () => {});
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
});
afterEach(() => {
  global.fetch = originalFetch;
  if (originalClipboard) Object.defineProperty(navigator, "clipboard", originalClipboard);
  else delete navigator.clipboard;
});
const finish = async (request, data) => { await act(async () => request.resolve(response(data))); };
const cannotExport = () => {
  const button = screen.queryByTestId("export-brief");
  if (button) {
    expect(button).toBeDisabled();
    fireEvent.click(button);
  }
  expect(writeText).not.toHaveBeenCalled();
  expect(screen.queryByText("SPY_OLD")).not.toBeInTheDocument();
};

test("a mounted ticker switch invalidates the previous brief while pending and after failure", async () => {
  const view = render(<BriefingStrip ticker="SPY" spot={600} />);
  await finish(requests[0], spy);
  expect(screen.getByText("SPY_OLD")).toBeInTheDocument();
  view.rerender(<BriefingStrip ticker="QQQ" spot={500} />);
  expect(requests.map(r => r.url.split("/").pop())).toEqual(["SPY", "QQQ"]);
  cannotExport();
  await act(async () => requests[1].reject(new Error("QQQ unavailable")));
  cannotExport();
});

test("only a matching new response exports its own identity, values and non-execution contract", async () => {
  const view = render(<BriefingStrip ticker="SPY" spot={600} />);
  await finish(requests[0], spy);
  view.rerender(<BriefingStrip ticker="QQQ" spot={500} />);
  cannotExport();
  await finish(requests[1], qqq);
  fireEvent.click(screen.getByTestId("export-brief"));
  expect(JSON.parse(writeText.mock.calls[0][0])).toEqual({
    brief: "floww-agent-brief.v1", ticker: "QQQ", asof: qqq.asof, spot: 500,
    executes_nothing: true,
    note: "Research draft for Public Agents (user paste + sign-off). Not an order.",
    metrics: qqq.metrics, regime: qqq.regime,
  });
  expect(await screen.findByTestId("export-brief-status")).toHaveTextContent("sign off there");
});

test.each(["resolve", "reject"])("an aborted SPY request cannot %s into the current QQQ state", async outcome => {
  const view = render(<BriefingStrip ticker="SPY" />);
  view.rerender(<BriefingStrip ticker="QQQ" />);
  expect(requests[0].signal.aborted).toBe(true);
  if (outcome === "resolve") await finish(requests[0], spy);
  else await act(async () => requests[0].reject(new Error("stale SPY failure")));
  cannotExport();
  await finish(requests[1], qqq);
  expect(screen.getByText("QQQ_CURRENT")).toBeInTheDocument();
  // A late response must also not overwrite already-resolved current data.
  fireEvent.click(screen.getByTestId("export-brief"));
  expect(JSON.parse(writeText.mock.calls[0][0]).metrics).toEqual(qqq.metrics);
  await screen.findByTestId("export-brief-status");
});

test("late SPY success cannot overwrite an already resolved QQQ brief", async () => {
  const view = render(<BriefingStrip ticker="SPY" />);
  view.rerender(<BriefingStrip ticker="QQQ" />);
  await finish(requests[1], qqq);
  await finish(requests[0], spy);
  expect(screen.getByText("QQQ_CURRENT")).toBeInTheDocument();
  expect(screen.queryByText("SPY_OLD")).not.toBeInTheDocument();
});

test.each(["resolve", "reject"])("old clipboard %s cannot publish copied/manual status on QQQ", async outcome => {
  const oldCopy = deferred();
  writeText.mockImplementation(() => oldCopy.promise);
  const view = render(<BriefingStrip ticker="SPY" />);
  await finish(requests[0], spy);
  fireEvent.click(screen.getByTestId("export-brief"));
  expect(JSON.parse(writeText.mock.calls[0][0]).ticker).toBe("SPY");
  view.rerender(<BriefingStrip ticker="QQQ" />);
  await finish(requests[1], qqq);
  await act(async () => outcome === "resolve" ? oldCopy.resolve() : oldCopy.reject(new Error("denied")));
  expect(screen.queryByTestId("export-brief-status")).not.toBeInTheDocument();
  expect(screen.queryByTestId("export-brief-text")).not.toBeInTheDocument();
  expect(screen.getByText("QQQ_CURRENT")).toBeInTheDocument();
});

test("switching away clears an existing manual draft", async () => {
  writeText.mockRejectedValue(new Error("denied"));
  const view = render(<BriefingStrip ticker="SPY" />);
  await finish(requests[0], spy);
  fireEvent.click(screen.getByTestId("export-brief"));
  expect(JSON.parse((await screen.findByTestId("export-brief-text")).value).ticker).toBe("SPY");
  view.rerender(<BriefingStrip ticker="QQQ" />);
  await finish(requests[1], qqq);
  expect(screen.queryByTestId("export-brief-text")).not.toBeInTheDocument();
  expect(screen.queryByTestId("export-brief-status")).not.toBeInTheDocument();
});

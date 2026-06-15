import { render, screen, waitFor } from "@testing-library/react";
import AlphaPodCapturePage from "./AlphaPodCapturePage";

// The component's liveness probe calls AbortSignal.timeout(); some jsdom builds
// don't implement it. Polyfill so the probe path itself is what's under test,
// not an environment gap.
beforeAll(() => {
  if (typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout !== "function") {
    AbortSignal.timeout = () => new AbortController().signal;
  }
});

beforeEach(() => {
  global.fetch = jest.fn();
});

afterEach(() => {
  jest.restoreAllMocks();
  delete global.fetch;
});

const SRC = "/captured/flow-alerts-live.html";

// REGRESSION GUARD: alphapod-hub omits Access-Control-Allow-Origin on static
// files, so a default (cors) fetch from the React origin is browser-blocked and
// the probe falsely reports "offline" even when :3456 is up. The fix is
// mode:"no-cors". This asserts the exact option that was missing in the bug.
test("liveness probe is issued with mode:'no-cors' (false-offline regression guard)", async () => {
  global.fetch.mockResolvedValue({ ok: true });
  render(<AlphaPodCapturePage src={SRC} label="Flow Alerts" />);
  await waitFor(() => expect(global.fetch).toHaveBeenCalled());
  expect(global.fetch).toHaveBeenCalledWith(
    "http://localhost:3456/favicon.svg",
    expect.objectContaining({ method: "HEAD", mode: "no-cors" })
  );
});

test("renders the iframe pointed at the full captured-page URL when the hub is reachable", async () => {
  global.fetch.mockResolvedValue({ ok: true });
  render(<AlphaPodCapturePage src={SRC} label="Flow Alerts" />);
  const frame = await screen.findByTitle("Flow Alerts");
  expect(frame).toHaveAttribute("src", "http://localhost:3456" + SRC);
});

test("shows the offline card (and no iframe) when the hub probe fails", async () => {
  global.fetch.mockRejectedValue(new TypeError("Failed to fetch"));
  render(<AlphaPodCapturePage src={SRC} label="Flow Alerts" />);
  expect(await screen.findByText(/server is not running/i)).toBeInTheDocument();
  expect(screen.queryByTitle("Flow Alerts")).toBeNull();
});

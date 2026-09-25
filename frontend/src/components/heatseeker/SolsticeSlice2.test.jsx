import React from "react";
import { render, screen, fireEvent, act } from "@testing-library/react";
import SkylitDashboard from "./SkylitDashboard";
import SolsticeStatusStrip from "./SolsticeStatusStrip";
import WallInspector from "./WallInspector";
import ScenarioStrip from "./ScenarioStrip";
import ReplayStrip from "./ReplayStrip";

jest.mock("axios");

const data = {
  ticker: "SPY",
  spot: 500,
  asof: new Date().toISOString(),
  exposure_basis: "OI",
  data_source: "public_api",
  mode: "day",
  expiries_used: ["2030-01-15"],
  strikes: [{ strike: 500, gex: 1e6, call_gex: 6e5, put_gex: 4e5 }],
  grid: { expiries: ["2030-01-15"], strikes: [500], grid: { "2030-01-15": { 500: 1e6 } } },
  nodes: { regime: "positive", king: { strike: 500, gex: 1e6 }, floors: [], ceilings: [] },
  metrics: {
    walls: [{ wall_id: "w_abc", low: 498, high: 502, mid: 500, gross: 2e6, net: 1e6, members: [498, 500, 502] }],
    nearest_walls: [{ wall_id: "w_abc", low: 498, high: 502, mid: 500, gross: 2e6, net: 1e6 }],
    grids: { delta: { grid: { "2030-01-15": { 500: 5e5 } }, expiries: ["2030-01-15"], exposure_basis: "OI_DELTA_WEIGHTED" } },
  },
  quality: { setupEligible: true, reasonCodes: [], state: "usable" },
};

test("metric switch renders and changes overlay basis", async () => {
  const axios = require("axios");
  axios.get.mockImplementation(async () => ({ data }));
  await act(async () => {
    render(<SkylitDashboard ticker="SPY" data={data} spot={500} />);
  });
  expect(screen.getByTestId("skylit-metric-switch")).toBeInTheDocument();
  await act(async () => {
    fireEvent.click(screen.getByTestId("skylit-metric-delta"));
  });
  expect(screen.getByTestId("skylit-grid-basis").textContent).toContain("OI_DELTA_WEIGHTED");
});

test("scale lock freezes the legend scale until scope change", async () => {
  const axios = require("axios");
  axios.get.mockImplementation(async () => ({ data }));
  await act(async () => {
    render(<SkylitDashboard ticker="SPY" data={data} spot={500} />);
  });
  await act(async () => {
    fireEvent.click(screen.getByTestId("skylit-scale-lock"));
  });
  expect(screen.getByTestId("skylit-scale-lock").textContent).toContain("Scale locked");
});

test("spot chip carries exact spot + offset", async () => {
  const axios = require("axios");
  axios.get.mockImplementation(async () => ({ data }));
  await act(async () => {
    render(<SkylitDashboard ticker="SPY" data={data} spot={500.4} />);
  });
  const chip = screen.getByTestId("skylit-spot-chip");
  expect(chip.title).toContain("500.40");
});

test("status strip shows Env/Loc/Setup/Data", () => {
  render(<SolsticeStatusStrip data={data} spot={501} ticker="SPY" isLive />);
  expect(screen.getByTestId("solstice-status-strip")).toBeInTheDocument();
  expect(screen.getByTestId("solstice-setup").textContent).toContain("Observe");
});

test("status strip shows WAIT on blocked setup", () => {
  const blocked = { ...data, quality: { setupEligible: false, reasonCodes: ["STALE_ASK"], state: "partial" } };
  render(<SolsticeStatusStrip data={blocked} spot={501} ticker="SPY" isLive={false} />);
  expect(screen.getByTestId("solstice-setup").textContent).toContain("Wait");
  expect(screen.getByTestId("solstice-data").textContent).toContain("degraded");
});

test("status chips select below/inside/above walls without scope change (R6-2)", () => {
  const onSelectWall = jest.fn();
  const { unmount } = render(<SolsticeStatusStrip
    data={{ ...data, metrics: { ...data.metrics,
      nearest_by_side: {
        below: { wall_id: "w_b", low: 490, high: 495 },
        inside: null,
        above: { wall_id: "w_a", low: 505, high: 510 },
      } } }}
    spot={500} ticker="SPY" isLive onSelectWall={onSelectWall} />);
  fireEvent.click(screen.getByTestId("solstice-chip-below"));
  expect(onSelectWall).toHaveBeenCalledWith(
    expect.objectContaining({ wall_id: "w_b" }));
  expect(screen.queryByTestId("solstice-chip-inside")).toBeNull();
  fireEvent.click(screen.getByTestId("solstice-chip-above"));
  expect(onSelectWall).toHaveBeenCalledWith(
    expect.objectContaining({ wall_id: "w_a" }));
  unmount();
});

test("wall inspector + scenarios render for selected wall", () => {
  render(<WallInspector wall={data.metrics.walls[0]} metrics={{ magnitude_ratio_delta_over_raw: 0.45, dadgex_usable: 10, dadgex_missing_delta: 2 }} grids={data.metrics.grids} quality={data.quality} />);
  expect(screen.getByTestId("wall-inspector")).toBeInTheDocument();
  // P05/R4-15: scope-wide ratio is labeled as scope-wide, never wall-local.
  expect(screen.getByText("Δ/Raw (scope)")).toBeInTheDocument();
  expect(screen.getByText("Δ provenance")).toBeInTheDocument();
  render(<ScenarioStrip scenarios={[{ name: "Bounce watch", confirmation: "reclaim", invalidation: "acceptance" }]} />);
  expect(screen.getByTestId("scenario-strip")).toBeInTheDocument();
});

test("same-wall compare differs between two unequal walls (R6-2)", () => {
  const React = require("react");
  const { render: r4, screen: s4, cleanup: c4 } = require("@testing-library/react");
  const WI2 = require("./WallInspector").default;
  const lo = { wall_id: "w_lo", low: 480, high: 482, gross: 1e6, net: 1e6, call: 1e6, put: 0 };
  const hi = { wall_id: "w_hi", low: 518, high: 522, gross: 1e6, net: 1e6, call: 1e6, put: 0 };
  const metrics = {
    wall_metrics: {
      w_lo: { daddex_gross: 500000, daddex_net: 500000, daddex_missing: 0, volume_net: 400000 },
      w_hi: { daddex_gross: 50000, daddex_net: 50000, daddex_missing: 0, volume_net: 40000 },
    },
  };
  r4(React.createElement(WI2, { wall: lo, metrics }));
  expect(s4.getByText(/Same-wall compare/)).toBeInTheDocument();
  const loText = s4.getByTestId("wall-inspector").textContent;
  expect(loText).toContain("$500.0K");
  c4();
  r4(React.createElement(WI2, { wall: hi, metrics }));
  expect(s4.getByTestId("wall-inspector").textContent).toContain("$50.0K");
});

test("wall inspector shows window activity or honest unavailability", () => {
  const { unmount } = render(<WallInspector wall={data.metrics.walls[0]} metrics={{}} />);
  expect(screen.getByText("Window activity")).toBeInTheDocument();
  expect(screen.getByText(/no comparable window/)).toBeInTheDocument();
  unmount();
  // R6-2: wall-local aggregation over member strikes — never the scope sum.
  render(<WallInspector wall={data.metrics.walls[0]}
    metrics={{ window_daddex_v1: 999999999, window_daddex_reason: null,
      wall_window: { w_abc: { window_daddex: 2500000,
        coverage: { member_strikes: 3, active_strikes: 2 } } } }} />);
  expect(screen.getByText(/window Δ-weighted/)).toBeInTheDocument();
  expect(screen.getByText(/2\/3 strikes/)).toBeInTheDocument();
  expect(screen.queryByText(/999999999|999,999,999/)).toBeNull();
});

test("status shows session block with Why-wait detail (R6-3)", () => {
  render(<SolsticeStatusStrip
    data={{ ...data, session: { entry_allowed: false, reasons: ["MARKET_CLOSED"] } }}
    spot={501} ticker="SPY" isLive />);
  expect(screen.getByTestId("solstice-setup").textContent).toContain("MARKET_CLOSED");
  expect(screen.getByTestId("solstice-setup").title).toContain("Why wait?");
});

test("inspector candidate section is read-only and optional (R6-3)", () => {
  const React = require("react");
  const { render: r5, screen: s5, cleanup: c5 } = require("@testing-library/react");
  const WI3 = require("./WallInspector").default;
  r5(React.createElement(WI3, {
    wall: data.metrics.walls[0],
    scout: { calls: 1, puts: 0, rejected: { STALE_ASK: [0, 2] } },
    patterns: [{ pattern_id: "mixed_structure", state: "CANDIDATE" }],
    regime: { sign: "POSITIVE" },
  }));
  expect(s5.getByText("0DTE candidates (read-only)")).toBeInTheDocument();
  expect(s5.getByText(/STALE_ASK/)).toBeInTheDocument();
  expect(s5.getByText("Pattern + regime context")).toBeInTheDocument();
  c5();
});

test("wall inspector shows OI dates and persistent sightings honestly", () => {
  const React = require("react");
  const { render: r3, screen: s3, cleanup: c3 } = require("@testing-library/react");
  const WI = require("./WallInspector").default;
  const h1 = r3(React.createElement(WI, {
    wall: { ...data.metrics.walls[0], oi_effective_dates: ["2030-01-01", "2030-01-02"] },
    interaction: { wall_id: "w_abc", state: "holding", event: "holding_confirmed", first_seen: false },
    quality: data.quality,
  }));
  expect(s3.getByText("2030-01-01, 2030-01-02")).toBeInTheDocument();
  expect(s3.getByText(/persistent/)).toBeInTheDocument();
  h1.unmount();
  c3();
  r3(React.createElement(WI, { wall: data.metrics.walls[0], quality: data.quality }));
  expect(s3.getByText("unavailable in snapshot")).toBeInTheDocument();
});

test("wall inspector shows interaction state and touches", () => {
  const React = require("react");
  const { render: r2, screen: s2 } = require("@testing-library/react");
  const WallInspector2 = require("./WallInspector").default;
  r2(React.createElement(WallInspector2, {
    wall: data.metrics.walls[0],
    interaction: { wall_id: "w_abc", state: "testing", event: "first_touch", taps: null },
    quality: data.quality,
  }));
  expect(s2.getByText("Interaction")).toBeInTheDocument();
  expect(s2.getByText("Touches")).toBeInTheDocument();
});

test("replay strip loads manifest", async () => {
  const axios = require("axios");
  axios.get.mockImplementation(async (url) => {
    if (String(url).includes("/attribute/")) {
      return { data: { status: "ok", strike_deltas: [{ strike: 500, delta: 1 }], walls_added: ["w_b"], walls_removed: [], volume_deltas: [], volume_rebased: [] } };
    }
    return { data: { snapshots: [{ id: "s1" }] } };
  });
  await act(async () => {
    render(<ReplayStrip ticker="SPY" />);
  });
  await act(async () => {
    fireEvent.click(screen.getByTestId("solstice-replay-load"));
  });
  expect(screen.getByTestId("solstice-replay-count").textContent).toContain("1 snapshots");
  await act(async () => {
    fireEvent.click(screen.getByTestId("solstice-compare-btn"));
  });
  expect(screen.getByTestId("solstice-compare-result").textContent).toContain("1 strikes");
});

test("replay strip shows truthful recorder badge (R6-3)", async () => {
  const axios = require("axios");
  axios.get.mockImplementation(async (url) => {
    if (String(url).includes("recorder_health")) {
      return { data: { durable: false, mode: "memory", tables: [] } };
    }
    return { data: { snapshots: [{ id: "s1" }] } };
  });
  await act(async () => {
    render(<ReplayStrip ticker="SPY" />);
  });
  await act(async () => {
    fireEvent.click(screen.getByTestId("solstice-replay-load"));
  });
  expect(screen.getByTestId("solstice-recorder-badge").textContent).toContain("memory");
});

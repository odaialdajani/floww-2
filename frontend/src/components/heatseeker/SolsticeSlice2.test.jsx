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
  // R7-05: the compressed string became a table; unequal walls still differ.
  expect(s4.getByTestId("wall-compare-table")).toBeInTheDocument();
  const loText = s4.getByTestId("wall-inspector").textContent;
  expect(loText).toContain("$500.0K");
  c4();
  r4(React.createElement(WI2, { wall: hi, metrics }));
  expect(s4.getByTestId("wall-inspector").textContent).toContain("$50.0K");
});

test("wall inspector shows window activity or honest unavailability", () => {
  const { unmount } = render(<WallInspector wall={data.metrics.walls[0]} metrics={{}} />);
  // R7-05: the standalone row folded into the comparison table; the
  // wall-local value (or its honest absence) still renders exactly once.
  const table = screen.getByTestId("wall-compare-table").textContent;
  expect(table).toContain("Recent window");
  expect(table).toContain("no comparable window");
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

test("mounted explainer renders five deterministic blocks (R6-4)", () => {
  const React = require("react");
  const { render: r6, screen: s6 } = require("@testing-library/react");
  const WI4 = require("./WallInspector").default;
  r6(React.createElement(WI4, {
    wall: { ...data.metrics.walls[0], gross: 2000000, net: 1000000 },
    snapshotId: "s9", metric: "raw", replay: false,
    interaction: { wall_id: "w_abc", state: "testing", first_seen: true },
    quality: data.quality,
  }));
  expect(s6.getByTestId("wall-explainer")).toBeInTheDocument();
  expect(s6.getByText("Why this wall.")).toBeInTheDocument();
  expect(s6.getByText("What limits the reading.")).toBeInTheDocument();
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

test("R7-05: same-wall comparison table shows both walls' own values", () => {
  const React = require("react");
  const { render: r7, screen: s7, cleanup: c7 } = require("@testing-library/react");
  const WI = require("./WallInspector").default;
  const mk = (id, low, gross, dd) => ({
    wall: { wall_id: id, low, high: low + 4, gross, net: gross / 2, call: gross, put: 0, members: [low, low + 2] },
    metrics: {
      wall_metrics: { [id]: { daddex_gross: dd, daddex_net: dd / 2, daddex_missing: 0, volume_gross: 7, volume_net: 7, volume_n: 2 } },
      wall_window: { [id]: { window_daddex: 3, coverage: { active_strikes: 2, member_strikes: 2 } } },
    },
    grids: { grid: { vex_grid: { "2030-01-15": { [low]: 11, [low + 2]: 22 } }, vex_meta: { status: "ok" } } },
  });
  const a = mk("w_a", 490, 2000000, 900000);
  r7(React.createElement(WI, { ...a, quality: data.quality }));
  const t1 = s7.getByTestId("wall-compare-table").textContent;
  expect(t1).toContain("$2.0M");
  expect(t1).toContain("$900.0K");
  c7();
  const b = mk("w_b", 510, 500000, 100000);
  r7(React.createElement(WI, { ...b, quality: data.quality }));
  const t2 = s7.getByTestId("wall-compare-table").textContent;
  expect(t2).toContain("$500.0K");
  expect(t2).toContain("$100.0K");
  expect(t2).not.toContain("$2.0M");
  expect(t2).toContain("local-bs-vanna.v1");
  c7();
});

test("R7-05: timeline and readiness derive from the interaction record", () => {
  const React = require("react");
  const { render: r7, screen: s7, cleanup: c7 } = require("@testing-library/react");
  const WI = require("./WallInspector").default;
  const base = { wall: data.metrics.walls[0], metrics: {}, quality: { setupEligible: true, reasonCodes: [], state: "usable" } };
  const ix = { state: "testing", event: "touch", at: "2030-01-02T14:05:00+00:00",
    approach_side: "above", inside_since: "2030-01-02T14:04:00+00:00", taps: 2, first_seen: false };
  r7(React.createElement(WI, { ...base, interaction: ix,
    scenario: { name: "Bounce watch", confirmation: "reclaim", invalidation: "accept" } }));
  expect(s7.getByTestId("wall-timeline").textContent).toContain("first touch");
  expect(s7.getByTestId("wall-timeline").textContent).toContain("from above");
  // Testing + eligible is not confirmation: Observe, not Confirmed.
  expect(s7.getByTestId("wall-readiness").textContent).toContain("Observe");
  c7();
  r7(React.createElement(WI, { ...base,
    interaction: { ...ix, state: "holding" },
    scenario: { name: "Bounce watch", confirmation: "reclaim", invalidation: "accept" } }));
  expect(s7.getByTestId("wall-readiness").textContent).toContain("Confirmed for review");
  c7();
  r7(React.createElement(WI, { ...base,
    interaction: { state: "invalidated", event: "accepted_below", adverse_side: "below" },
    quality: { setupEligible: false, reasonCodes: ["X"], state: "partial" } }));
  expect(s7.getByTestId("wall-readiness").textContent).toContain("Invalidated");
  c7();
  // False eligibility without reasons: Wait with a generic blocker.
  r7(React.createElement(WI, { ...base, interaction: { state: "testing" },
    quality: { setupEligible: false, reasonCodes: [], state: "unavailable" } }));
  const w = s7.getByTestId("wall-readiness").textContent;
  expect(w).toContain("Wait");
  expect(w).toContain("reason unavailable");
  c7();
});

test("R7-05: shortlist rows are tagged to the selected wall; empty explains", () => {
  const React = require("react");
  const { render: r7, screen: s7, cleanup: c7 } = require("@testing-library/react");
  const WI = require("./WallInspector").default;
  const scout = {
    calls: 2, puts: 0, rejected: { STALE_ASK: [3, 1] },
    shortlist: {
      CALLS: [
        { osi: "OC1", expiry: "2030-01-15", strike: 500, side: "CALLS", delta: 0.45,
          bid: 1.0, ask: 1.2, spread_pct: 18.2, tick_size: null, tick_unknown: true,
          bid_ts: "2030-01-02T14:00:00+00:00", ask_ts: "2030-01-02T14:00:00+00:00" },
        { osi: "OC9", expiry: "2030-01-15", strike: 600, side: "CALLS", delta: 0.42,
          bid: 0.5, ask: 0.6, spread_pct: 18.2, tick_size: null, tick_unknown: true,
          bid_ts: null, ask_ts: null },
      ],
      PUTS: [],
    },
  };
  r7(React.createElement(WI, { wall: data.metrics.walls[0], metrics: {},
    quality: data.quality, scout }));
  expect(s7.getByTestId("shortlist-calls").textContent).toContain("1/2 in this wall");
  const rows = s7.getAllByTestId("shortlist-row");
  expect(rows.length).toBe(2);
  expect(rows[0].textContent).toContain("●");
  expect(rows[1].textContent).toContain("○");
  expect(rows[0].textContent).toContain("tick unknown");
  expect(rows[0].textContent).toContain("14:00:00");
  c7();
  r7(React.createElement(WI, { wall: data.metrics.walls[0], metrics: {},
    quality: data.quality, scout: { calls: 0, puts: 0, rejected: { STALE_ASK: [5, 0] } } }));
  expect(s7.getByTestId("shortlist-empty").textContent).toContain("withheld setup is a valid result");
  expect(s7.getByTestId("shortlist-empty").textContent).toContain("rejection counts above");
  c7();
});

test("R7-05: advanced shows real vanna and moneyness values, not placeholders", () => {
  const React = require("react");
  const { render: r7, screen: s7, cleanup: c7 } = require("@testing-library/react");
  const WI = require("./WallInspector").default;
  r7(React.createElement(WI, { wall: data.metrics.walls[0], metrics: {},
    quality: data.quality,
    vanna: { by_expiry: { "2030-01-15": { vanna: 1234.5, vomma: 10, n: 4 } } },
    moneyness: { buckets: { call_atm: { oi: 2000000, volume: 5, n: 3 } } } }));
  const adv = s7.getByTestId("advanced-values").textContent;
  expect(adv).toContain("01-15");
  expect(adv).toContain("call_atm");
  expect(adv).not.toContain("view present");
  c7();
});

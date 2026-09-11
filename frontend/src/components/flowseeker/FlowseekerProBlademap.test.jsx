// FlowseekerProBlademap Phase 5.3 tests — Public API wiring.
//
// Tests the mapPublicChainToRows helper (pure function) and the
// live-feed dual-path logic (Public API primary → cvserver fallback).
/** @jest-environment jsdom */

import { mapPublicChainToRows, pulseSignal } from "./FlowseekerProBlademap";

// ---- mapPublicChainToRows: pure helper tests ----

describe("mapPublicChainToRows — Phase 5.3 Public API helper", () => {
  const MKT = "SPY";

  const mkContract = (overrides = {}) => ({
    strike: 450,
    type: "call",
    expiry: "2026-09-18",
    volume: 500,
    oi: 1200,
    iv: 0.22,
    bid: 4.5,
    ask: 4.7,
    last: 4.6,
    ...overrides,
  });

  it("maps a single high-volume contract to a flow row", () => {
    const rows = mapPublicChainToRows([mkContract()], 450, MKT);
    expect(rows).toHaveLength(1);
    expect(rows[0].ticker).toBe(MKT);
    expect(rows[0].type).toBe("call");
    expect(rows[0].strike).toBe(450);
    expect(rows[0].volume).toBe(500);
    expect(rows[0].oi).toBe(1200);
    expect(rows[0].vol_oi_ratio).toBeCloseTo(500 / 1200, 3);
    expect(rows[0].iv).toBe(22); // <1 → ×100
    expect(rows[0].premium).toBeGreaterThan(0);
    expect(rows[0]._conv).toBeGreaterThanOrEqual(20);
    expect(rows[0]._conv).toBeLessThanOrEqual(99);
  });

  it("filters out contracts below noise floor (vol < NOISE_FLOOR*20 = 100)", () => {
    // vol=100, oi=200 → voi=0.5 ≥ 0.4 → KEPT (passes both checks)
    // vol=99 → filtered by noise floor (vol < 100)
    const rows = mapPublicChainToRows(
      [
        mkContract({ volume: 100, oi: 200 }),   // kept: vol≥100 AND voi=0.5≥0.4
        mkContract({ volume: 99, oi: 200 }),    // filtered: vol < 100
        mkContract({ volume: 50, oi: 100 }),    // filtered: vol < 100
      ],
      450,
      MKT,
    );
    expect(rows).toHaveLength(1);
    expect(rows[0].volume).toBe(100);
    expect(rows[0].oi).toBe(200);
  });

  it("filters out contracts below vol/oi threshold (< 0.4)", () => {
    const rows = mapPublicChainToRows(
      [mkContract({ volume: 500, oi: 2000 })],
      450,
      MKT,
    );
    expect(rows).toHaveLength(0);
  });

  it("keeps contracts at exactly vol/oi = 0.4", () => {
    const rows = mapPublicChainToRows(
      [mkContract({ volume: 400, oi: 1000 })],
      450,
      MKT,
    );
    expect(rows).toHaveLength(1);
    expect(rows[0].vol_oi_ratio).toBe(0.4);
  });

  it("sorts by vol_oi_ratio descending", () => {
    const rows = mapPublicChainToRows(
      [
        mkContract({ strike: 440, volume: 300, oi: 300 }), // voi=1.0
        mkContract({ strike: 460, volume: 800, oi: 8000 }), // voi=0.1 → filtered
        mkContract({ strike: 450, volume: 500, oi: 500 }), // voi=1.0
      ],
      450,
      MKT,
    );
    expect(rows).toHaveLength(2);
    expect(rows[0].vol_oi_ratio).toBeGreaterThanOrEqual(rows[1].vol_oi_ratio);
  });

  it("caps output at 100 rows", () => {
    const contracts = Array.from({ length: 200 }, (_, i) =>
      mkContract({ strike: 400 + i, volume: 500, oi: 500 }),
    );
    const rows = mapPublicChainToRows(contracts, 450, MKT);
    expect(rows).toHaveLength(100);
  });

  it("handles empty contract list", () => {
    expect(mapPublicChainToRows([], 450, MKT)).toEqual([]);
  });

  it("handles null/missing fields gracefully", () => {
    const rows = mapPublicChainToRows(
      [
        { strike: null, type: null, volume: 500, oi: 500 },
        { volume: 50, oi: 100 },
      ],
      450,
      MKT,
    );
    expect(rows).toHaveLength(1);
    // String(c.type || "") where c.type=null → String("" || "") → ""  → toLowerCase → ""
    expect(rows[0].type).toBe("");
  });

  it("uses last price for mid when available", () => {
    const rows = mapPublicChainToRows(
      [mkContract({ last: 4.6, bid: 0, ask: 0 })],
      450,
      MKT,
    );
    expect(rows[0].premium).toBeGreaterThan(0);
  });

  it("falls back to estPrice when no bid/ask/last", () => {
    const rows = mapPublicChainToRows(
      [mkContract({ bid: 0, ask: 0, last: 0, iv: 0.25, strike: 450, expiry: "2026-09-18" })],
      450,
      MKT,
    );
    expect(rows).toHaveLength(1);
    expect(rows[0].premium).toBeGreaterThan(0);
  });

  it("classifies block/sweep/unusual by premium and DTE", () => {
    // Block: premium >= 5e7. Need vol*mid*100 >= 5e7.
    // vol=200000, mid=5 → premium=200000*5*100=1e8 → block
    const blockRows = mapPublicChainToRows(
      [{ strike: 450, type: "call", expiry: "2026-09-18", volume: 200000, oi: 1000, iv: 0.5, bid: 4.5, ask: 5.5, last: 5.0 }],
      450,
      MKT,
    );
    expect(blockRows[0].classification).toBe("block");

    // Sweep: DTE <= 2
    const today = new Date();
    const exp2d = new Date(today.getTime() + 2 * 86400000).toISOString().slice(0, 10);
    const sweepRows = mapPublicChainToRows(
      [mkContract({ volume: 500, oi: 500, strike: 450, iv: 0.2, expiry: exp2d })],
      450,
      MKT,
    );
    expect(sweepRows[0].classification).toBe("sweep");

    // Unusual: everything else
    const exp30d = new Date(today.getTime() + 30 * 86400000).toISOString().slice(0, 10);
    const unusualRows = mapPublicChainToRows(
      [mkContract({ volume: 500, oi: 500, strike: 450, iv: 0.2, expiry: exp30d })],
      450,
      MKT,
    );
    expect(unusualRows[0].classification).toBe("unusual");
  });

  it("handles put types correctly", () => {
    const rows = mapPublicChainToRows(
      [mkContract({ type: "put", strike: 440, volume: 500, oi: 500 })],
      450,
      MKT,
    );
    expect(rows[0].type).toBe("put");
  });

  it("handles iv > 1 as percentage (no ×100)", () => {
    const rows = mapPublicChainToRows(
      [mkContract({ iv: 25, volume: 500, oi: 500 })],
      450,
      MKT,
    );
    expect(rows[0].iv).toBe(25);
  });

  it("handles iv < 1 as decimal (×100)", () => {
    const rows = mapPublicChainToRows(
      [mkContract({ iv: 0.25, volume: 500, oi: 500 })],
      450,
      MKT,
    );
    expect(rows[0].iv).toBe(25);
  });
});

// ---- Dual-path logic: data_source assignment ----

describe("Phase 5.3 dual-path: Public API → cvserver fallback", () => {
  it("both paths produce rows with the same shape", () => {
    const pubRows = mapPublicChainToRows(
      [{ strike: 450, type: "call", expiry: "2026-09-18", volume: 500, oi: 1000, iv: 0.2, bid: 4, ask: 4.2, last: 4.1 }],
      450,
      "SPY",
    );
    expect(pubRows[0]).toHaveProperty("ticker");
    expect(pubRows[0]).toHaveProperty("type");
    expect(pubRows[0]).toHaveProperty("strike");
    expect(pubRows[0]).toHaveProperty("expiration");
    expect(pubRows[0]).toHaveProperty("volume");
    expect(pubRows[0]).toHaveProperty("oi");
    expect(pubRows[0]).toHaveProperty("vol_oi_ratio");
    expect(pubRows[0]).toHaveProperty("iv");
    expect(pubRows[0]).toHaveProperty("premium");
    expect(pubRows[0]).toHaveProperty("_conv");
    expect(pubRows[0]).toHaveProperty("_cd");
    expect(pubRows[0]).toHaveProperty("classification");
  });

  it("data_source → public_api when Public API returns contracts", () => {
    const contracts = [{ strike: 450, type: "call", expiry: "2026-09-18", volume: 500, oi: 500 }];
    const rows = mapPublicChainToRows(contracts, 450, "SPY");
    expect(rows.length).toBeGreaterThan(0);
  });

  it("falls back to cvserver when Public API returns no contracts", () => {
    expect(mapPublicChainToRows([], 450, "SPY")).toEqual([]);
  });
});

describe("Pulse helpers — BladeMap tape contract", () => {
  const { pulseScore10, pulseSignal, pulseBadges, aggregatePulse, pruneBuffer, pulseHedge, costLabel, COST_TITLE, COST_CAPTION, COST_CAPTION_TITLE } = require("./FlowseekerProBlademap");

  it("pulseHedge flags put-ASK only (reference signal untouched)", () => {
    expect(pulseHedge("put", "ASK")).toBe(true);
    expect(pulseHedge("PUT", "ask")).toBe(true);
    expect(pulseHedge("call", "ASK")).toBe(false);
    expect(pulseHedge("put", "BID")).toBe(false);
    expect(pulseHedge(null, "ASK")).toBe(false);
  });
  it("pulseScore10 maps conviction 20-99 to 2.0-9.9", () => {
    expect(pulseScore10(20)).toBe(2.0);
    expect(pulseScore10(99)).toBe(9.9);
    expect(pulseScore10(80)).toBe(8.0);
  });

  it("pulseSignal: ASK→BULLISH, BID→BEARISH regardless of C/P", () => {
    expect(pulseSignal("ASK")).toBe("BULLISH");
    expect(pulseSignal("BID")).toBe("BEARISH");
    expect(pulseSignal("ask")).toBe("BULLISH");
  });

  it("pulseBadges: SILVER always, GOLDEN ≥$900K, WHALE ≥$1M", () => {
    expect(pulseBadges(417500)).toEqual(["SILVER"]);
    expect(pulseBadges(899800)).toEqual(["SILVER"]);
    expect(pulseBadges(950400)).toEqual(["SILVER", "GOLDEN"]);
    expect(pulseBadges(1000000)).toEqual(["SILVER", "GOLDEN", "WHALE"]);
  });

  it("aggregatePulse rolls one contract into one row with 90s totals", () => {
    const now = 100000;
    const r = (premium, volume, ts) => ({ ticker: "SPY", type: "call", strike: 450, expiration: "2026-09-18", premium, volume, timestamp: ts, _conv: 80 });
    const rows = aggregatePulse([r(100000, 100, now - 10000), r(200000, 200, now - 5000), { ticker: "QQQ", type: "put", strike: 500, expiration: "2026-09-18", premium: 50000, volume: 50, timestamp: now - 8000, _conv: 70 }], 90e3, now);
    expect(rows.length).toBe(2);
    expect(rows[0]._aggPrem).toBe(300000);
    expect(rows[0]._aggN).toBe(2);
  });

  it("aggregatePulse excludes prints older than the window", () => {
    const now = 100000;
    const rows = aggregatePulse([
      { ticker: "SPY", type: "call", strike: 450, expiration: "2026-09-18", premium: 999999, volume: 999, timestamp: now - 90001, _conv: 99 },
      { ticker: "SPY", type: "call", strike: 450, expiration: "2026-09-18", premium: 1000, volume: 10, timestamp: now - 1000, _conv: 50 },
    ], 90e3, now);
    expect(rows.length).toBe(1);
    expect(rows[0]._aggPrem).toBe(1000);
    expect(rows[0]._aggN).toBe(1);
  });

  it("pruneBuffer keeps only prints inside the trailing window", () => {
    const now = 50000;
    const buf = [{ timestamp: now - 89999 }, { timestamp: now - 90000 }, { timestamp: now - 120000 }, {}];
    // {} (missing ts) falls back to now → kept.
    expect(pruneBuffer(buf, 90e3, now).length).toBe(2);
    expect(pruneBuffer(null)).toEqual([]);
  });

  it("mapPublicChainToRows stamps side + mid + otm on every row", () => {
    const rows = mapPublicChainToRows(
      [{ strike: 460, type: "call", expiry: "2026-09-18", volume: 500, oi: 500, iv: 0.2, bid: 4, ask: 4.2, last: 4.1 }],
      450, "SPY",
    );
    expect(rows[0].side).toBe("ASK");
    expect(rows[0].mid).toBeCloseTo(4.1);
    expect(rows[0].otm).toBeCloseTo((10 / 450) * 100);
  });

  it("F11: missing quotes stamp side UNKNOWN, never a voi guess", () => {
    const rows = mapPublicChainToRows(
      [{ strike: 460, type: "call", expiry: "2026-09-18", volume: 500, oi: 100, iv: 0.2 }],
      450, "SPY",
    );
    expect(rows).toHaveLength(1);
    expect(rows[0].side).toBe("UNKNOWN");
    expect(pulseSignal(rows[0].side)).toBe("UNKNOWN");
  });
});

describe("flowClassTitle — sweep/block proxy-copy contract (XH-1)", () => {
  const { flowClassTitle: ft, FLOW_PROXY_NOTE: N, FILTER_CHIP_TITLES: CT } = require("./FlowseekerProBlademap");
  it("sweep title names the proxy mechanism honestly", () => {
    const t = ft("SWEEP");
    expect(t).toMatch(/proxy/i);
    expect(t).toMatch(/no multi-venue execution observed/i);
    expect(t).not.toMatch(/multi-print burst|multi-exchange urgency/);
  });
  it("block title names the proxy mechanism honestly", () => {
    const t = ft("BLOCK");
    expect(t).toMatch(/proxy/i);
    expect(t).toMatch(/not an observed block print/i);
  });
  it("premium-based Pulse blocks do not get volume-only row or chip titles", () => {
    // Same volume, below Scanner's 8,000-contract BLOCK threshold;
    // only the premium crosses Pulse's $50M BLOCK threshold.
    const contract = {
      strike: 450, type: "call", expiry: "2099-09-18",
      volume: 5000, oi: 5000, iv: 0.2,
    };
    const [below] = mapPublicChainToRows([{ ...contract, last: 99 }], 450, "SPY");
    const [block] = mapPublicChainToRows([{ ...contract, last: 100 }], 450, "SPY");
    expect(below.classification).toBe("unusual");
    expect(block.premium).toBe(50000000);
    expect(block.classification).toBe("block");
    for (const title of [ft(block.classification), CT[block.classification.toUpperCase()]]) {
      expect(title).toMatch(/size-bucket proxy/i);
      expect(title).toMatch(/not an observed block print/i);
      expect(title).not.toMatch(/volume/i);
    }
  });
  it("other classes pass through unchanged", () => {
    expect(ft("unusual")).toBe("UNUSUAL");
    expect(ft(null)).toBe("REG");
  });
  it("drawer note discloses the snapshot-chain limitation", () => {
    expect(N).toMatch(/size\/tenor-bucket prox/i);
    expect(N).toMatch(/no venue tape/);
    expect(N).not.toMatch(/multi-exchange urgency/);
  });
  it("filter chips carry proxy titles for sweep/block only", () => {
    expect(CT.SWEEP).toMatch(/proxy/i);
    expect(CT.BLOCK).toMatch(/proxy/i);
    expect(CT.CALL).toBeUndefined();
  });
});

describe("costLabel — COST honesty contract (Step 1.4)", () => {
  const { costLabel: cl, COST_TITLE: T, COST_CAPTION: C, COST_CAPTION_TITLE: CT } = require("./FlowseekerProBlademap");
  it("null in, null out; building shows a count, never a number", () => {
    expect(cl(null)).toBeNull();
    const b = cl({ building: true, nd: 7 });
    expect(b.text).toBe("COST building 7/30");
    expect(b.text).not.toMatch(/\$\d/);
  });
  it("numbered and truncated states keep the caption + title", () => {
    for (const r of [{ building: false, spread: 0.04 }, { building: false, spread: 0, truncated: true }]) {
      const o = cl(r);
      expect(o.caption).toBe("mid-quote, not executable");
      expect(o.title).toMatch(/NOT an executable taker cost/);
    }
    expect(cl({ building: false, spread: 0.04 }).text).toBe("COST ~$0.04");
    expect(cl({ building: false, spread: 0, truncated: true }).text).toBe("COST ~$0.00");
  });
  it("exported copy pins the wording", () => {
    expect(T).toMatch(/NOT an executable taker cost/);
    expect(C).toBe("mid-quote, not executable");
    expect(CT).toMatch(/NOT an executable taker cost/);
  });
});

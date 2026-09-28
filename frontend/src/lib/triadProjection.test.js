/**
 * Triad projection audit pins.
 *
 * Each test names the defect it prevents. The first test also runs the OLD
 * inline transform (copied verbatim from the pre-fix component body) on the
 * same input and asserts it disagrees, so these cannot pass by accident.
 */

import {
  TRIAD_PROJECTION_VERSION,
  projectTriadFromChain,
} from "./triadProjection";

const EXP_A = "2030-01-15";
const EXP_B = "2030-02-19";

function contract(overrides = {}) {
  return {
    strike: 100,
    expiry: EXP_A,
    type: "call",
    gex: 100,
    oi: 10,
    volume: 1,
    iv: 0.2,
    delta: 0.5,
    gamma: 0.01,
    vanna: 0.03,
    charm: -0.02,
    T: 30 / 365,
    ...overrides,
  };
}

function payload(contracts, overrides = {}) {
  return {
    ok: true,
    ticker: "SPY",
    spot: 100,
    expiries: [EXP_A, EXP_B],
    n_contracts: contracts.length,
    data_source: "public_api",
    stale: false,
    contracts,
    ...overrides,
  };
}

/** The pre-fix inline transform, kept so the regression is demonstrable. */
function legacyInlineTransform(pubRes, dteFilter) {
  const contracts = pubRes.contracts || [];
  const grid = { grid: { "0": {} } };
  for (const c of contracts.slice(0, 200)) {
    const expKey = c.expiry || "2026-09-18";
    if (!grid.grid[expKey]) grid.grid[expKey] = {};
    grid.grid[expKey][String(c.strike)] = {
      gex: c.gex,
      iv: c.iv,
      delta: c.delta,
      charm: c.charm,
      vanna: c.vanna,
      vex: 0,
      call_gex: c.gex >= 0 ? c.gex : 0,
      put_gex: c.gex < 0 ? c.gex : 0,
    };
  }
  const strikes = contracts.map((c) => ({ strike: c.strike, gex: c.gex }));
  return {
    grid,
    strikes,
    change_pct: 0,
    vix: 20,
    expiries_used: [...new Set(contracts.map((c) => c.expiry).filter(Boolean))].slice(0, dteFilter),
  };
}

describe("triad projection: opposing contracts aggregate, never overwrite", () => {
  const opposing = [
    contract({ type: "call", gex: 100 }),
    contract({ type: "put", gex: -60 }),
  ];

  test("a call and a put at one strike net to +40, not the last writer's -60", () => {
    const legacy = legacyInlineTransform(payload(opposing), 3);
    // The old code wrote one slot per (expiry, strike) with no side dimension,
    // so the put clobbered the call.
    expect(legacy.grid.grid[EXP_A]["100"].gex).toBe(-60);

    const out = projectTriadFromChain(payload(opposing), { expiryCount: 3 });
    expect(out.grid.grid[EXP_A]["100"].gex).toBe(40);
    expect(out.grid.grid[EXP_A]["100"].call_gex).toBe(100);
    expect(out.grid.grid[EXP_A]["100"].put_gex).toBe(-60);
  });

  test("the per-strike row is one row per strike, not one per contract", () => {
    const out = projectTriadFromChain(payload(opposing), { expiryCount: 3 });
    expect(out.strikes).toHaveLength(1);
    expect(out.strikes[0].gex).toBe(40);
    expect(out.strikes[0].oi).toBe(20);
  });

  test("king is an aggregated strike, not a single contract row", () => {
    const out = projectTriadFromChain(
      payload([
        contract({ strike: 100, type: "call", gex: 100 }),
        contract({ strike: 100, type: "put", gex: -60 }),
        contract({ strike: 105, type: "call", gex: 30 }),
      ]),
      { expiryCount: 3 },
    );
    expect(out.nodes.king).toEqual({ strike: 100, gex: 40 });
  });
});


describe("triad projection: no fabricated time axis", () => {
  test("no '0' placeholder expiry survives into the grid", () => {
    const legacy = legacyInlineTransform(payload([contract()]), 3);
    expect(Object.keys(legacy.grid.grid)).toContain("0");

    const out = projectTriadFromChain(payload([contract()]), { expiryCount: 3 });
    expect(Object.keys(out.grid.grid)).toEqual([EXP_A]);
    expect(Object.keys(out.grid.grid)).not.toContain("0");
    expect(out.expiries_used).toEqual([EXP_A]);
  });

  test("the '0' key would displace a real expiry column, and no longer can", () => {
    const six = ["2030-01-15", "2030-02-19", "2030-03-19", "2030-04-16", "2030-05-21", "2030-06-18"];
    const contracts = [
      contract({ expiry: "" }),
      ...six.map((e, i) => contract({ expiry: e, strike: 100 + i, gex: 10 })),
    ];
    const out = projectTriadFromChain(payload(contracts), { expiryCount: 10 });
    // Sorted keys with a "0" present would render "0" first and hide one date.
    expect(out.expiries_used).toEqual(six);
    expect(out.expiries_used).toHaveLength(6);
  });

  test("a contract with no expiry is dropped and counted, never dated", () => {
    const out = projectTriadFromChain(
      payload([contract(), contract({ osi: "X", expiry: "" })]),
      { expiryCount: 3 },
    );
    expect(out.coverage.dropped_no_expiry).toBe(1);
    expect(Object.keys(out.grid.grid)).toEqual([EXP_A]);
    expect(JSON.stringify(out)).not.toContain("2026-09-18");
  });

  test("expiry count and DTE are reported separately, not conflated", () => {
    const out = projectTriadFromChain(
      payload([
        contract({ expiry: EXP_A, T: 1 / 365 }),
        contract({ expiry: EXP_B, T: 45 / 365 }),
      ]),
      { expiryCount: 1 },
    );
    expect(out.coverage.expiries_requested).toBe(1);
    expect(out.coverage.expiries_available).toBe(2);
    expect(out.coverage.expiries_used).toBe(1);
    expect(out.coverage.expiry_cap_applied).toBe(true);
    expect(out.coverage.expiries_dropped_by_cap).toBe(1);
    expect(out.coverage.truncated).toBe(true);
  });

  test("truncation is declared rather than silent", () => {
    const many = Array.from({ length: 250 }, (_, i) =>
      contract({ strike: 100 + i, expiry: EXP_A, gex: 1 }),
    );
    const legacy = legacyInlineTransform(payload(many), 3);
    expect(Object.keys(legacy.grid.grid[EXP_A])).toHaveLength(200);

    const out = projectTriadFromChain(payload(many), { expiryCount: 3 });
    expect(out.coverage.returned).toBe(250);
    expect(Object.keys(out.grid.grid[EXP_A])).toHaveLength(250);
  });
});


describe("triad projection: unknown stays unknown", () => {
  test("unmeasured VEX is null, not a measured zero", () => {
    const legacy = legacyInlineTransform(payload([contract()]), 3);
    expect(legacy.grid.grid[EXP_A]["100"].vex).toBe(0);

    const out = projectTriadFromChain(payload([contract()]), { expiryCount: 3 });
    expect(out.grid.grid[EXP_A]["100"].vex).toBeNull();
  });

  test("synthetic VIX and change percent are not invented", () => {
    const legacy = legacyInlineTransform(payload([contract()]), 3);
    expect(legacy.vix).toBe(20);
    expect(legacy.change_pct).toBe(0);

    const out = projectTriadFromChain(payload([contract()]), { expiryCount: 3 });
    expect(out.vix).toBeNull();
    expect(out.change_pct).toBeNull();
  });

  test("no zero-gamma root is inferred from adjacent bucket sign changes", () => {
    const out = projectTriadFromChain(
      payload([
        contract({ strike: 100, type: "call", gex: 50 }),
        contract({ strike: 105, type: "put", gex: -50 }),
      ]),
      { expiryCount: 3 },
    );
    expect(out.nodes.gamma_flip).toBeNull();
  });

  test("polarity is not |exposure| divided by spot", () => {
    const out = projectTriadFromChain(payload([contract({ gex: 1234 })]), { expiryCount: 3 });
    expect(out.nodes.polarity_level).toBeNull();
    expect(out.nodes.net_gex).toBe(1234);
  });

  test("a contract without measured gex writes no cell rather than a zero", () => {
    const out = projectTriadFromChain(
      payload([contract({ gex: null })]),
      { expiryCount: 3 },
    );
    expect(out.grid.grid[EXP_A]["100"].gex).toBeNull();
    expect(out.coverage.contracts_without_gex).toBe(1);
    expect(out.coverage.usable).toBe(0);
  });

  test("call and put Greeks are not blended into one number", () => {
    const out = projectTriadFromChain(
      payload([
        contract({ type: "call", iv: 0.2, delta: 0.55 }),
        contract({ type: "put", iv: 0.3, delta: -0.45 }),
      ]),
      { expiryCount: 3 },
    );
    const cell = out.grid.grid[EXP_A]["100"];
    expect(cell.iv).toBeNull();
    expect(cell.delta).toBeNull();
    expect(cell.call_iv).toBe(0.2);
    expect(cell.put_iv).toBe(0.3);
    // A single-sided cell IS unambiguous, so it reports the real value.
    const single = projectTriadFromChain(payload([contract({ iv: 0.2, delta: 0.55 })]), {
      expiryCount: 3,
    });
    expect(single.grid.grid[EXP_A]["100"].iv).toBe(0.2);
    expect(single.grid.grid[EXP_A]["100"].delta).toBe(0.55);
  });
});


describe("triad projection: honest metadata", () => {
  test("packet is versioned and carries provenance", () => {
    const out = projectTriadFromChain(payload([contract()], { stale: true }), { expiryCount: 3 });
    expect(out.projection_version).toBe(TRIAD_PROJECTION_VERSION);
    expect(out.data_source).toBe("public_api");
    expect(out.stale).toBe(true);
    expect(() => JSON.stringify(out)).not.toThrow();
    const round = JSON.parse(JSON.stringify(out));
    expect(round.grid.grid[EXP_A]["100"].vex).toBeNull();
    expect(round.coverage.returned).toBe(1);
  });

  test("unknown side and bad strike are counted, not silently signed", () => {
    const out = projectTriadFromChain(
      payload([
        contract({ type: "future", gex: 10 }),
        contract({ strike: 0, gex: 10 }),
        contract({ strike: "bad", gex: 10 }),
      ]),
      { expiryCount: 3 },
    );
    expect(out.coverage.dropped_unknown_side).toBe(1);
    expect(out.coverage.dropped_bad_strike).toBe(2);
    expect(out.strikes).toHaveLength(0);
  });

  test("empty input yields an unavailable grid, not a zero-filled one", () => {
    const out = projectTriadFromChain(payload([]), { expiryCount: 3 });
    expect(out.grid.grid).toEqual({});
    expect(out.expiries_used).toEqual([]);
    expect(out.strikes).toEqual([]);
    expect(out.nodes.net_gex).toBeNull();
  });
});

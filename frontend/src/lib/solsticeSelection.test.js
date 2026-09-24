import { resolveSelectedWall, wallPositionOf } from "./solsticeSelection";

function snap(ticker, asof, walls) {
  return {
    ticker, asof,
    metrics: { walls },
    interactions: walls.map((w) => ({ wall_id: w.wall_id, state: "testing" })),
    scenarios: walls.flatMap((w) => ([
      { wall_id: w.wall_id, name: `watch ${w.wall_id}` },
      { wall_id: w.wall_id, name: `continuation ${w.wall_id}` },
    ])),
  };
}

const W1 = { wall_id: "w_aaa", low: 490, high: 495, mid: 492.5, gross: 15e6, net: 1e6 };
const W2 = { wall_id: "w_bbb", low: 505, high: 510, mid: 507.5, gross: 12e6, net: -2e6 };

describe("solsticeSelection (P05/R4-06)", () => {
  test("second-wall selection resolves its own wall + scenarios", () => {
    const data = snap("SPY", "t1", [W1, W2]);
    const r = resolveSelectedWall(data, { ticker: "SPY", asof: "t1", wall_id: "w_bbb", strike: 507 });
    expect(r.status).toBe("ok");
    expect(r.wall.wall_id).toBe("w_bbb");
    expect(r.interaction.wall_id).toBe("w_bbb");
    expect(r.scenarios.length).toBe(2);
    expect(r.scenarios.every((s) => s.wall_id === "w_bbb")).toBe(true);
  });

  test("refresh (asof change) retains by identity with current values", () => {
    const d1 = snap("SPY", "t1", [W1, W2]);
    const sel = { ticker: "SPY", asof: "t1", wall_id: "w_bbb", strike: 507 };
    const r1 = resolveSelectedWall(d1, sel);
    expect(r1.wall.wall_id).toBe("w_bbb");
    const W2b = { ...W2, gross: 13e6 };
    const d2 = snap("SPY", "t2", [W1, W2b]);
    const r2 = resolveSelectedWall(d2, sel);
    expect(r2.status).toBe("ok");
    expect(r2.wall.wall_id).toBe("w_bbb");
    expect(r2.wall.gross).toBe(13e6);
  });

  test("metric switch keeps the wall (identity, not nearest)", () => {
    const data = snap("SPY", "t1", [W1, W2]);
    const r = resolveSelectedWall(data, { ticker: "SPY", wall_id: "w_aaa" });
    expect(r.wall.wall_id).toBe("w_aaa");
  });

  test("cross-symbol clears immediately", () => {
    const data = snap("QQQ", "t1", [W1]);
    const r = resolveSelectedWall(data, { ticker: "SPY", wall_id: "w_aaa" });
    expect(r.status).toBe("cleared");
    expect(r.wall).toBeNull();
  });

  test("missing wall explains WALL_GONE, never substitutes", () => {
    const data = snap("SPY", "t2", [W1]);
    const r = resolveSelectedWall(data, { ticker: "SPY", wall_id: "w_bbb" });
    expect(r.status).toBe("gone");
    expect(r.reason).toBe("WALL_GONE");
    expect(r.wall).toBeNull();
  });

  test("wallPositionOf matches backend vocabulary", () => {
    expect(wallPositionOf(W1, 500)).toBe("below");
    expect(wallPositionOf(W2, 500)).toBe("above");
    expect(wallPositionOf({ low: 498, high: 502 }, 500)).toBe("inside");
  });
});

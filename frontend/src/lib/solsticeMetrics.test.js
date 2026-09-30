import {
  GEX_BASES, baseDef, sectionFor, surfaceStatus, sumProfile, wallValues, wallRead, NEAR_ZERO_SHARE,
} from "./solsticeMetrics";

const EXP1 = "2031-01-17";
const EXP2 = "2031-01-24";

function payload() {
  return {
    ticker: "SPY", spot: 100,
    grid: { expiries: [EXP1, EXP2], strikes: [95, 100, 105],
      grid: { [EXP1]: { 95: 50000, 100: 100000, 105: -100000 }, [EXP2]: { 100: 20000 } } },
    metrics: {
      grids: {
        raw: null,
        delta: { expiries: [EXP1], grid: { [EXP1]: { 95: 12500, 100: 50000 } },
          cell_missing_delta: { [EXP1]: { 105: 1 } }, missing_delta: 1, status: "ok" },
        session_delta_volume: { expiries: [EXP1], grid: { [EXP1]: { 95: 1000, 100: 5000 } },
          cell_missing_delta: { [EXP1]: { 105: 1 } }, status: "ok" },
        activity: { expiries: [EXP1], grid: { [EXP1]: { 95: 4000, 100: 10000, 105: -10000 } }, status: "ok" },
        window: { status: "unavailable", reason: "NO_BASELINE", grid: null },
      },
      surface_coverage: {
        raw: { status: "ok", usable: 3 },
        delta: { status: "partial", usable: 2, missing_delta: 1 },
        window: { status: "unavailable", reason: "NO_BASELINE", usable: 0 },
      },
      wall_metrics: {
        w1: { daddex_gross: 50000, daddex_net: 50000, daddex_usable: 1, daddex_missing: 0,
          volume_gross: 10000, volume_net: 10000, volume_usable: 1, volume_missing: 0,
          sdv_gross: 5000, sdv_net: 5000, sdv_usable: 1, sdv_missing_delta: 0 },
        w2: { daddex_gross: 0, daddex_net: 0, daddex_usable: 0, daddex_missing: 1,
          volume_gross: 10000, volume_net: -10000, volume_usable: 1 },
      },
    },
  };
}

test("primary GEX bases retain the integrated compact labels and distinct activity formula", () => {
  expect(GEX_BASES.map((b) => b.label)).toEqual(["Raw OI", "Δ-weighted OI", "Volume × |Δ|"]);
  // The legacy Σc·u·V surface is NOT labelled as delta-weighted anywhere.
  expect(baseDef("activity").label).not.toMatch(/×\s*\|?Δ/);
  expect(baseDef("session_delta_volume").basis).toBe("VOLUME_DELTA_WEIGHTED");
  expect(baseDef("activity").basis).toBe("VOLUME");
});

test("sectionFor maps each basis to its own backend section, never raw", () => {
  const p = payload();
  expect(sectionFor(p, "raw")).toBe(p.grid);
  expect(sectionFor(p, "session_delta_volume")).toBe(p.metrics.grids.session_delta_volume);
  expect(sectionFor(p, "activity")).toBe(p.metrics.grids.activity);
  delete p.metrics.grids.session_delta_volume;
  expect(sectionFor(p, "session_delta_volume")).toBeNull();
});

test("surfaceStatus prefers backend coverage and keeps partial visible", () => {
  const p = payload();
  expect(surfaceStatus(p, "delta")).toMatchObject({ status: "partial", missing: 1, usable: 2 });
  expect(surfaceStatus(p, "window")).toMatchObject({ status: "unavailable", reason: "NO_BASELINE" });
  // Older packet without surface_coverage: falls back to the section.
  delete p.metrics.surface_coverage;
  expect(surfaceStatus(p, "delta").status).toBe("partial");
  expect(surfaceStatus(p, "window").status).toBe("unavailable");
});

test("sumProfile sums one surface over the declared scope; gaps stay null", () => {
  const p = payload();
  const all = sumProfile(p, "raw", [EXP1, EXP2]);
  expect(all.values["100"]).toBe(120000);
  expect(all.values["105"]).toBe(-100000);
  const one = sumProfile(p, "raw", [EXP2]);
  expect(one.values["100"]).toBe(20000);
  expect(one.values["95"]).toBeUndefined(); // gap, not zero
  const d = sumProfile(p, "delta", [EXP1, EXP2]);
  expect(d.values["105"]).toBeUndefined();
  expect(d.partial["105"]).toBe(1);
  expect(d.maxAbs).toBe(50000);
  expect(sumProfile(p, "window", [EXP1]).available).toBe(false);
});

test("wallValues reads same-wall families; zero usable is unknown not $0", () => {
  const p = payload();
  const v1 = wallValues(p, { wall_id: "w1", gross: 150000, net: 150000 });
  expect(v1.session_delta_volume.net).toBe(5000);
  expect(v1.delta.net).toBe(50000);
  const v2 = wallValues(p, { wall_id: "w2", gross: 100000, net: -100000 });
  expect(v2.delta.net).toBeNull();
  expect(v2.delta.missing).toBe(1);
  expect(v2.session_delta_volume).toBeNull(); // older packet: no sdv fields
});

const OK_Q = { setupEligible: true, reasonCodes: [] };

test.each([
  [{ low: 95, high: 97 }, 100, 5000, "Bounce watch", "positive"],
  [{ low: 103, high: 105 }, 100, 5000, "Rejection watch", "positive"],
  [{ low: 95, high: 97 }, 100, -5000, "Downside continuation watch", "negative"],
  [{ low: 103, high: 105 }, 100, -5000, "Upside continuation watch", "negative"],
])("wallRead names a conditional watch from position × adjusted sign", (wall, spot, adj, watch, tone) => {
  const r = wallRead({ wall: { wall_id: "w", ...wall }, spot, adjNet: adj, adjAvailable: true,
    rawGross: 20000, interaction: null, quality: OK_Q });
  expect(r.watch).toBe(watch);
  expect(r.tone).toBe(tone);
  // Unobserved price interaction never reads as ready.
  expect(r.readiness).toBe("Observe");
});

test("wallRead: measured interaction controls readiness; gaps hold at Wait", () => {
  const wall = { wall_id: "w", low: 95, high: 97 };
  const confirmed = wallRead({ wall, spot: 100, adjNet: 5000, adjAvailable: true, rawGross: 20000,
    interaction: { state: "holding" }, quality: OK_Q });
  expect(confirmed.readiness).toBe("Confirmed for review");
  const blocked = wallRead({ wall, spot: 100, adjNet: 5000, adjAvailable: true, rawGross: 20000,
    interaction: { state: "holding" }, quality: { setupEligible: false, reasonCodes: ["STALE_CHAIN"] } });
  expect(blocked.readiness).toBe("Wait");
  expect(blocked.reasons).toContain("STALE_CHAIN");
  const noAdj = wallRead({ wall, spot: 100, adjNet: null, adjAvailable: false, rawGross: 20000,
    interaction: { state: "holding" }, quality: OK_Q });
  expect(noAdj.watch).toBeNull();
  expect(noAdj.readiness).toBe("Wait");
  const inval = wallRead({ wall, spot: 100, adjNet: 5000, adjAvailable: true, rawGross: 20000,
    interaction: { state: "invalidated" }, quality: OK_Q });
  expect(inval.readiness).toBe("Invalidated");
});

test("wallRead: near-zero adjusted net is two-sided, not a signed watch", () => {
  const r = wallRead({ wall: { wall_id: "w", low: 95, high: 97 }, spot: 100,
    adjNet: (NEAR_ZERO_SHARE / 2) * 100000, adjAvailable: true, rawGross: 100000,
    interaction: null, quality: OK_Q });
  expect(r.watch).toBeNull();
  expect(r.tone).toBe("flat");
});

test("wallRead output never contains order, target, stop or dealer-intent language", () => {
  const texts = [];
  for (const adj of [5000, -5000, null]) {
    for (const wall of [{ low: 95, high: 97 }, { low: 103, high: 105 }, { low: 99, high: 101 }]) {
      const r = wallRead({ wall: { wall_id: "w", ...wall }, spot: 100, adjNet: adj,
        adjAvailable: adj != null, rawGross: 20000, interaction: null, quality: OK_Q });
      texts.push(r.watch || "", ...r.reasons);
    }
  }
  const joined = texts.join(" | ");
  expect(joined).not.toMatch(/\b(buy|sell|order|target|stop|dealers? (will|must|want))\b/i);
});

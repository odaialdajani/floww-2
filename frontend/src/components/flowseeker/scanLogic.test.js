import {
  bizDTE, scanTypeOf, scanScoreOf, estimateDelta, approxSpot, mkScanRow,
  fmtUSD, fmtK, fmtIV, scoreGradeOf, estPremium, evalAlerts, tickerRollup,
  archetypeOf, volSigma, annotateFirstSeen, sessionDay, fmtClock, fmtAge,
  awaySummary, scanRowsToCSV, oiChange, streakOf, isTradingDay, evalTickerAlerts,
  pulseState, elapsedClock, formatFOLLOWStrip,
  tierOf, selectFires, pickBanner, spreadPosition, overviewStats,
  equityType, signedOtm, isOpexDay, highlightState, flagSpreadLegs,
  interpDeltaIV, skewLevels, pinRisk, quoteSkew, midDrift, stampPollDeltas, nearestExpiryPin,
  rollSpread, pushCapped, rollPooled, contractKey, signedBias,
} from "./scanLogic";

describe("signedBias mirrors the server desk matrix (A2 parity)", () => {
  // Same 5 contracts both sides: backend side_bias (public_scanner) and
  // engine infer_side_bias (flow_alerts) must agree with this table.
  const cases = [
    ["call", "ASK", "BUY", "BULLISH"],
    ["put", "ASK", "BUY", "BEARISH"],
    ["call", "BID", "SELL", "BEARISH"],
    ["put", "BID", "SELL", "BULLISH"],
    ["call", null, "FLOW", null],
  ];
  it.each(cases)("%s + %s → %s / %s", (type, signed, side, bias) => {
    expect(signedBias(type, signed)).toEqual({ side, bias });
  });
  it("unknown garbage stays unlabeled", () => {
    expect(signedBias("call", "MAYBE")).toEqual({ side: "FLOW", bias: null });
  });
});

describe("estimateDelta", () => {
  it("is ~±0.5 at the money", () => {
    expect(Math.abs(estimateDelta(100, 100, "call"))).toBeCloseTo(0.5, 1);
    expect(Math.abs(estimateDelta(100, 100, "put"))).toBeCloseTo(0.5, 1);
  });
  it("calls: deep ITM → +1ish, deep OTM → 0ish; puts mirror negatively", () => {
    expect(estimateDelta(50, 100, "call")).toBeGreaterThan(0.9);
    expect(estimateDelta(150, 100, "call")).toBeLessThan(0.1);
    expect(estimateDelta(150, 100, "put")).toBeLessThan(-0.9);
    expect(estimateDelta(50, 100, "put")).toBeGreaterThan(-0.1);
  });
  it("returns null without a spot", () => {
    expect(estimateDelta(100, null, "call")).toBeNull();
    expect(estimateDelta(null, 100, "call")).toBeNull();
  });
});

describe("IV unit heuristic (decimal IVs above 100% are real)", () => {
  it("fmtIV treats <3 as decimal, ≥3 as pct", () => {
    expect(fmtIV(1.5)).toBe("150.0%");
    expect(fmtIV(0.42)).toBe("42.0%");
    expect(fmtIV(42)).toBe("42.0%");
  });
  it("estPremium has no /100 cliff at iv=1.5 (meme-stock IV)", () => {
    const base = { strike: 100, vol: 1000, dte: 5, delta: 0.5 };
    const p075 = estPremium({ ...base, iv: 0.75 });
    const p150 = estPremium({ ...base, iv: 1.5 });
    expect(p150).toBeCloseTo(p075 * 2, 5);   // linear in iv — not divided by 100
  });
});

describe("approxSpot", () => {
  it("is the median strike", () => {
    expect(approxSpot([110, 90, 100])).toBe(100);
    expect(approxSpot([])).toBeNull();
    expect(approxSpot(null)).toBeNull();
  });
});

describe("scanTypeOf thresholds", () => {
  it("classifies by volume magnitude then vol/OI", () => {
    expect(scanTypeOf({ vol: 30000, volOI: 1 })).toBe("sweep");
    expect(scanTypeOf({ vol: 9000, volOI: 1 })).toBe("block");
    expect(scanTypeOf({ vol: 500, volOI: 2.5 })).toBe("unusual");
    expect(scanTypeOf({ vol: 500, volOI: 1.2 })).toBe("split");
    expect(scanTypeOf({ vol: 500, volOI: 0.2 })).toBe("regular");
  });
});

describe("scanScoreOf regime nudge", () => {
  const base = { volOI: 2, vol: 5000, notional: 5e6, dte: 2, delta: 0.3 };
  it("negative gamma boosts short-dated flow", () => {
    const plain = scanScoreOf({ ...base });
    const nudged = scanScoreOf({ ...base }, "negative");
    expect(nudged).toBeGreaterThan(plain);
    expect(nudged).toBeLessThanOrEqual(100);
  });
  it("positive gamma boosts fresh positioning (vol/OI ≥ 2)", () => {
    expect(scanScoreOf({ ...base }, "positive")).toBeGreaterThan(scanScoreOf({ ...base }));
  });
  it("records component parts on the row", () => {
    const r = { ...base };
    scanScoreOf(r, "negative");
    expect(r._parts.nudge).toBe(5);
    expect(r._parts.pos).toBeGreaterThan(0);
  });
  it("informed-positioning band (7-90 DTE, vol≥3×OI, ≥$25k) adds +4", () => {
    const inBand = { volOI: 3.5, vol: 5000, notional: 5e6, premium: 1e5, dte: 30, delta: 0.3 };
    scanScoreOf(inBand);
    expect(inBand._parts.band).toBe(4);
    const noFloor = { ...inBand, premium: 5e3 };
    scanScoreOf(noFloor);
    expect(noFloor._parts.band).toBe(0);
    const tooShort = { ...inBand, dte: 3 };
    scanScoreOf(tooShort);
    expect(tooShort._parts.band).toBe(0);
  });
});

describe("mkScanRow", () => {
  it("computes notional, volOI, dte, score and estimates delta from spot", () => {
    const r = mkScanRow("NVDA", "call", 120, "2099-01-08", 10000, 4000, 0.5, null, 118, "negative");
    expect(r.notional).toBe(10000 * 100 * 120);
    expect(r.volOI).toBeCloseTo(2.5);
    expect(r.deltaEst).toBe(true);
    expect(r.delta).not.toBeNull();
    expect(r.regime).toBe("negative");
    expect(r.score).toBeGreaterThan(0);
    expect(r._parts).toBeDefined();
    expect(r.ftype).toBe("block");
  });
  it("keeps a real delta when provided", () => {
    const r = mkScanRow("SPY", "put", 740, "2099-01-08", 2000, 1000, 0.2, -0.35, 744, null);
    expect(r.delta).toBe(-0.35);
    expect(r.deltaEst).toBe(false);
  });
  it("no spot + no delta → delta stays null, OTM component degrades gracefully", () => {
    const r = mkScanRow("TSLA", "call", 300, "2099-01-08", 5000, 1000, 0.6, null, null, null);
    expect(r.delta).toBeNull();
    expect(r.deltaEst).toBe(false);
    expect(r.score).toBeGreaterThan(0);
  });
});

describe("formatters", () => {
  it("fmtUSD / fmtK / fmtIV / scoreGradeOf", () => {
    expect(fmtUSD(2.5e9)).toBe("$2.50B");
    expect(fmtK(1500)).toBe("2k");
    expect(fmtIV(0.42)).toBe("42.0%");
    expect(scoreGradeOf(85)).toBe("crit");
    expect(scoreGradeOf(40)).toBe("norm");
  });
});

describe("estPremium", () => {
  it("null without iv or strike", () => {
    expect(estPremium({ iv: null, strike: 100, vol: 10, dte: 5 })).toBeNull();
    expect(estPremium({ iv: 0.3, strike: 0, vol: 10, dte: 5 })).toBeNull();
  });
  it("scales with volume and iv, handles pct-style iv", () => {
    const base = { strike: 100, vol: 1000, dte: 5, delta: 0.5 };
    const p1 = estPremium({ ...base, iv: 0.2 });
    const p2 = estPremium({ ...base, iv: 0.4 });
    const p2pct = estPremium({ ...base, iv: 40 });   // 40 ≡ 40%
    expect(p2).toBeGreaterThan(p1);
    expect(p2pct).toBeCloseTo(p2, 5);
    expect(estPremium({ ...base, iv: 0.2, vol: 2000 })).toBeCloseTo(p1 * 2, 5);
  });
  it("discounts deep OTM via delta, never below the floor price", () => {
    const atm = estPremium({ strike: 100, vol: 100, dte: 5, iv: 0.3, delta: 0.5 });
    const otm = estPremium({ strike: 100, vol: 100, dte: 5, iv: 0.3, delta: 0.05 });
    expect(otm).toBeLessThan(atm);
    expect(estPremium({ strike: 1, vol: 100, dte: 1, iv: 0.01, delta: 0.02 })).toBeGreaterThanOrEqual(100 * 100 * 0.05);
  });
});

describe("evalAlerts", () => {
  const mk = (over) => ({
    under: "SPY", type: "call", strike: 745, exp: "2099-01-08",
    score: 93, premium: 2e6, notional: 5e7, volOI: 3, dte: 5, _new: true, ...over,
  });
  it("only fires on _new rows", () => {
    expect(evalAlerts([mk({ _new: false })])).toEqual([]);
    expect(evalAlerts([mk()])).toHaveLength(1);
  });
  it("SCORE rule respects minScore", () => {
    const hits = evalAlerts([mk({ score: 84 }), mk({ score: 85, strike: 750 })], { minScore: 85 });
    expect(hits).toHaveLength(1);
    expect(hits[0].rule).toBe("SCORE");
    expect(hits[0].strike).toBe(750);
  });
  it("WHALE fires on premium threshold when score is quiet", () => {
    const hits = evalAlerts([mk({ score: 40, premium: 12e6 })], { minScore: 85, whalePremium: 10e6 });
    expect(hits).toHaveLength(1);
    expect(hits[0].rule).toBe("WHALE");
  });
  it("PRIME fires in the 55-62% bracket below the SCORE bar (SNDK gap)", () => {
    const hits = evalAlerts([mk({ score: 82, premium: 600e3, volOI: 6 })]);
    expect(hits).toHaveLength(1);
    expect(hits[0].rule).toBe("PRIME");
    expect(hits[0].key).toBe("prime|SPY|call|745|2099-01-08");
  });
  it("PRIME stays off below the $250k / 5x floors", () => {
    expect(evalAlerts([mk({ score: 82, premium: 100e3, volOI: 6 })])).toEqual([]);
    expect(evalAlerts([mk({ score: 82, premium: 600e3, volOI: 2 })])).toEqual([]);
  });
  it("PRIME yields to SCORE and WHALE (size first)", () => {
    expect(evalAlerts([mk({ score: 95, premium: 600e3, volOI: 6 })])[0].rule).toBe("SCORE");
    expect(evalAlerts([mk({ score: 40, premium: 30e6, volOI: 8 })])[0].rule).toBe("WHALE");
    expect(evalAlerts([mk({ score: 40, premium: 5e6, volOI: 8 })])[0].rule).toBe("PRIME");
  });
  it("0DTE fires on short-dated near-threshold flow", () => {
    const hits = evalAlerts([mk({ score: 72, premium: 1e5, dte: 0 })], { minScore: 85, zeroDteScore: 70 });
    expect(hits).toHaveLength(1);
    expect(hits[0].rule).toBe("0DTE");
  });
  it("disabled rules are skipped and each row alerts at most once", () => {
    const rows = [mk({ score: 99, premium: 99e6, dte: 0 })];
    expect(evalAlerts(rows, { enabled: { score: false, whale: false, zerodte: false } })).toEqual([]);
    expect(evalAlerts(rows)).toHaveLength(1);   // matches SCORE first, not three times
  });
  it("carries a rule-namespaced key plus the raw contract key", () => {
    const [hit] = evalAlerts([mk()]);
    expect(hit.key).toBe("score|SPY|call|745|2099-01-08");   // dedup ttls stay per-rule
    expect(hit.ckey).toBe("SPY|call|745|2099-01-08");
  });
  it("omitted-opts callers inherit post-tightening gates (92/$25M/6σ-era)", () => {
    // SCORE: 91 silent, 93 fires.
    expect(evalAlerts([mk({ score: 91, premium: 1e5 })])).toEqual([]);
    expect(evalAlerts([mk({ score: 93, premium: 1e5 })])).toHaveLength(1);
    // WHALE: $24M silent, $26M fires (score quiet).
    expect(evalAlerts([mk({ score: 40, premium: 24e6 })])).toEqual([]);
    expect(evalAlerts([mk({ score: 40, premium: 26e6 })])[0].rule).toBe("WHALE");
  });
  it("0DTE needs score>=85 AND volOI>=2 (lotto shut out)", () => {
    expect(evalAlerts([mk({ score: 84, premium: 1e5, dte: 0, volOI: 5 })])).toEqual([]);
    expect(evalAlerts([mk({ score: 86, premium: 1e5, dte: 0, volOI: 1 })])).toEqual([]);
    const hits = evalAlerts([mk({ score: 86, premium: 1e5, dte: 0, volOI: 3 })]);
    expect(hits).toHaveLength(1);
    expect(hits[0].rule).toBe("0DTE");
  });
});

describe("evalAlerts universe fully open (no allowlist)", () => {
  const rows = [
    { _new: true, under: "SPY", type: "call", strike: 750, exp: "2099-01-08", score: 95, premium: 1e6, dte: 5 },
    { _new: true, under: "ZZTOP", type: "put", strike: 10, exp: "2099-01-08", score: 99, premium: 1e6, dte: 5 },
  ];
  it("fires for a non-universe ticker with default opts (whole market)", () => {
    const hits = evalAlerts([rows[1]]);
    expect(hits).toHaveLength(1);
    expect(hits[0].under).toBe("ZZTOP");
    expect(hits[0].rule).toBe("SCORE");
  });
  it("a legacy allow opt is accepted but ignored — both rows still fire", () => {
    expect(evalAlerts(rows, { allow: ["SPY", "QQQ"] })).toHaveLength(2);
    expect(evalAlerts(rows, { allow: [] })).toHaveLength(2);
    expect(evalAlerts(rows, {})).toHaveLength(2);
  });
});

describe("oiChange", () => {
  it("returns fractional pct and absolute delta vs prior-day OI", () => {
    expect(oiChange(14200, 10000)).toEqual({ abs: 4200, pct: 0.42 });
    expect(oiChange(6000, 10000)).toEqual({ abs: -4000, pct: -0.4 });
  });
  it("null when there is no prior record or prior OI was zero", () => {
    expect(oiChange(10000, null)).toBeNull();
    expect(oiChange(10000, 0)).toBeNull();
    expect(oiChange(null, 10000)).toBeNull();
  });
});

describe("awaySummary", () => {
  const H = 3600e3;
  const now = 100 * H;
  const log = [
    { rule: "SCORE", t: now - 1 * H },
    { rule: "WHALE", t: now - 2 * H },
    { rule: "SCORE", t: now - 50 * H },   // before the away window
  ];
  const rows = [
    { under: "NVDA", score: 100, firstSeen: now - 1 * H },
    { under: "SPY", score: 90, firstSeen: now - 30 * H },   // seen before window
    { under: "TSLA", score: 96, firstSeen: now - 2 * H },
    { under: "QQQ", score: 97, firstSeen: now - 3 * H },
    { under: "AMD", score: 80, firstSeen: now - 1 * H },
  ];
  it("counts only alerts after sinceMs and returns top-3 new rows by score", () => {
    const s = awaySummary(log, rows, now - 4 * H, now);
    expect(s.nAlerts).toBe(2);
    expect(s.counts).toEqual({ SCORE: 1, WHALE: 1 });
    expect(s.topNew.map((r) => r.under)).toEqual(["NVDA", "QQQ", "TSLA"]);
    expect(s.gapMs).toBe(4 * H);
  });
  it("null when the gap is under the threshold or there is nothing to report", () => {
    expect(awaySummary(log, rows, now - 10 * 60e3, now)).toBeNull();       // 10min < 30min
    expect(awaySummary([], [], now - 4 * H, now)).toBeNull();              // nothing happened
    expect(awaySummary(log, rows, null, now)).toBeNull();                  // first ever visit
  });
});

describe("scanRowsToCSV", () => {
  it("emits a header plus one line per row and ISO first-seen", () => {
    const csv = scanRowsToCSV([{ firstSeen: Date.UTC(2026, 6, 10, 14, 30), score: 95, under: "SPY", type: "call", strike: 750, exp: "2026-07-10", dte: 0, vol: 1000, oi: 500, volOI: 2, premium: 12345, notional: 1e6, iv: 0.22, ftype: "SWEEP", arch: "WHALE", lean: "BULL", regime: "positive" }]);
    const lines = csv.split("\n");
    expect(lines).toHaveLength(2);
    expect(lines[0]).toBe("seen,score,ticker,type,strike,expiry,dte,volume,oi,oi_chg_pct,vol_oi,premium_est,notional,iv,flow,archetype,lean,regime");
    expect(lines[1]).toContain("2026-07-10T14:30:00.000Z,95,SPY,call,750");
  });
  it("escapes commas/quotes and blanks nulls", () => {
    const csv = scanRowsToCSV([{ under: 'A"B', ftype: "x,y", score: null }]);
    expect(csv.split("\n")[1]).toContain('"A""B"');
    expect(csv.split("\n")[1]).toContain('"x,y"');
    expect(csv.split("\n")[1].startsWith(",")).toBe(true);   // null firstSeen → empty
  });
});

describe("annotateFirstSeen", () => {
  it("stamps the first sighting and preserves it across refreshes same session", () => {
    const t1 = new Date(2026, 6, 6, 10, 0, 0).getTime();
    const t2 = new Date(2026, 6, 6, 10, 5, 0).getTime();
    const rows1 = [{ under: "SPY", type: "call", strike: 745, exp: "2099-01-08" }];
    const { seen } = annotateFirstSeen(rows1, null, t1);
    expect(rows1[0].firstSeen).toBe(t1);
    const rows2 = [{ under: "SPY", type: "call", strike: 745, exp: "2099-01-08" }];
    annotateFirstSeen(rows2, seen, t2);
    expect(rows2[0].firstSeen).toBe(t1);   // preserved, not re-stamped
  });
  it("resets the map when the trading day rolls", () => {
    const t1 = new Date(2026, 6, 6, 10, 0, 0).getTime();
    const t2 = new Date(2026, 6, 7, 10, 0, 0).getTime();
    const rows1 = [{ under: "SPY", type: "call", strike: 745, exp: "2099-01-08" }];
    const { seen } = annotateFirstSeen(rows1, null, t1);
    expect(seen.day).toBe("2026-07-06");
    const rows2 = [{ under: "SPY", type: "call", strike: 745, exp: "2099-01-08" }];
    const out = annotateFirstSeen(rows2, seen, t2);
    expect(out.seen.day).toBe("2026-07-07");
    expect(rows2[0].firstSeen).toBe(t2);   // fresh session → fresh stamp
  });
  it("new contracts get the current time; tolerates empty input", () => {
    const now = new Date(2026, 6, 6, 11, 0, 0).getTime();
    expect(annotateFirstSeen([], null, now).rows).toEqual([]);
    const rows = [{ under: "AAPL", type: "put", strike: 200, exp: "2099-02-01" }];
    const { seen } = annotateFirstSeen(rows, { day: sessionDay(now), map: {} }, now);
    expect(rows[0].firstSeen).toBe(now);
    expect(seen.map["AAPL|put|200|2099-02-01"]).toBe(now);
  });
});

describe("fmtClock / fmtAge", () => {
  it("fmtClock returns — for null and a time string otherwise", () => {
    expect(fmtClock(null)).toBe("—");
    const s = fmtClock(new Date(2026, 6, 6, 13, 5, 0).getTime());
    expect(typeof s).toBe("string");
    expect(s.length).toBeGreaterThan(3);
  });
  it("fmtAge buckets seconds / minutes / hours", () => {
    const now = 10_000_000;
    expect(fmtAge(now - 5000, now)).toBe("5s");
    expect(fmtAge(now - 120000, now)).toBe("2m");
    expect(fmtAge(now - 7200000, now)).toBe("2h");
    expect(fmtAge(null, now)).toBe("—");
  });
});

describe("volSigma", () => {
  it("z-scores today's volume against the baseline", () => {
    expect(volSigma(150000, { avg: 100000, std: 20000, days: 5 })).toBeCloseTo(2.5);
    expect(volSigma(80000, { avg: 100000, std: 20000, days: 5 })).toBeCloseTo(-1.0);
  });
  it("null without a usable baseline", () => {
    expect(volSigma(150000, null)).toBeNull();
    expect(volSigma(150000, { avg: 100000, std: 0, days: 5 })).toBeNull();
    expect(volSigma(150000, { avg: 100000, std: 20000, days: 1 })).toBeNull();
    expect(volSigma(null, { avg: 100000, std: 20000, days: 5 })).toBeNull();
  });
});

describe("archetypeOf", () => {
  it("WHALE on ≥$10M estimated premium (first match wins)", () => {
    expect(archetypeOf({ premium: 12e6, delta: 0.1, dte: 1, volOI: 5, type: "call" })).toBe("WHALE");
  });
  it("LOTTO on deep-OTM short-dated", () => {
    expect(archetypeOf({ premium: 1e5, delta: 0.08, dte: 1, volOI: 1, type: "call" })).toBe("LOTTO");
    expect(archetypeOf({ premium: 1e5, delta: -0.12, dte: 2, volOI: 1, type: "put" })).toBe("LOTTO");
  });
  it("HEDGE on mid-delta long-dated puts", () => {
    expect(archetypeOf({ premium: 1e5, delta: -0.4, dte: 45, volOI: 1, type: "put" })).toBe("HEDGE");
    expect(archetypeOf({ premium: 1e5, delta: 0.4, dte: 45, volOI: 1, type: "call" })).toBeNull();
  });
  it("FRESH on vol/OI ≥ 3 with the $25k retail-noise premium floor", () => {
    expect(archetypeOf({ premium: 1e5, delta: 0.5, dte: 10, volOI: 3.5, type: "call" })).toBe("FRESH");
    expect(archetypeOf({ premium: 5e3, delta: 0.5, dte: 10, volOI: 3.5, type: "call" })).toBeNull();
    expect(archetypeOf({ premium: null, delta: 0.5, dte: 10, volOI: 3.5, type: "call" })).toBe("FRESH"); // no estimate ≠ small
  });
  it("null when nothing distinctive; tolerates missing fields", () => {
    expect(archetypeOf({ premium: 1e5, delta: 0.5, dte: 10, volOI: 1, type: "call" })).toBeNull();
    expect(archetypeOf({ volOI: 1, type: "call" })).toBeNull();
  });
  it("mkScanRow attaches arch", () => {
    const r = mkScanRow("SPY", "call", 745, "2099-01-08", 60000, 4000, 0.9, 0.5, 744, null);
    expect(r.arch).toBe("WHALE");
  });
});

describe("tickerRollup", () => {
  const row = (under, type, premium, score = 50, regime = null) => ({ under, type, premium, score, regime });
  it("aggregates premium per ticker, sorted desc, top-N", () => {
    const out = tickerRollup([
      row("SPY", "call", 5e6), row("SPY", "put", 3e6),
      row("QQQ", "call", 20e6), row("NVDA", "put", 1e6),
    ], 2);
    expect(out.map((e) => e.under)).toEqual(["QQQ", "SPY"]);
    expect(out[1].prem).toBe(8e6);
  });
  it("computes call% split and carries max score + regime", () => {
    const [spy] = tickerRollup([
      row("SPY", "call", 6e6, 91, "negative"), row("SPY", "put", 2e6, 55),
    ]);
    expect(spy.callPct).toBe(75);
    expect(spy.maxScore).toBe(91);
    expect(spy.regime).toBe("negative");
    expect(spy.count).toBe(2);
  });
  it("computes volume-based PCR (Pan-Poteshman) per ticker", () => {
    const r = (type, vol) => ({ under: "SPY", type, premium: 1e5, score: 50, regime: null, vol });
    const [spy] = tickerRollup([r("call", 4000), r("put", 1000), r("put", 1000)]);
    expect(spy.pcr).toBeCloseTo(0.5);
    const [noCalls] = tickerRollup([r("put", 1000)]);
    expect(noCalls.pcr).toBeNull();
  });
  it("handles null premiums and empty input", () => {
    expect(tickerRollup([])).toEqual([]);
    const [t] = tickerRollup([row("TSLA", "call", null)]);
    expect(t.prem).toBe(0);
    expect(t.callPct).toBe(50);
  });
});

describe("bizDTE", () => {
  it("expired → 0, null → null", () => {
    expect(bizDTE("2000-01-01")).toBe(0);
    expect(bizDTE(null)).toBeNull();
  });
  it("expiring today → 0 regardless of time of day (date-boundary based)", () => {
    const t = new Date();
    const today = `${t.getUTCFullYear()}-${String(t.getUTCMonth() + 1).padStart(2, "0")}-${String(t.getUTCDate()).padStart(2, "0")}`;
    expect(bizDTE(today)).toBe(0);
  });
  it("tomorrow is at most 1 trading day away", () => {
    const t = new Date(Date.now() + 86400000);
    const tomorrow = `${t.getUTCFullYear()}-${String(t.getUTCMonth() + 1).padStart(2, "0")}-${String(t.getUTCDate()).padStart(2, "0")}`;
    const d = bizDTE(tomorrow);
    expect(d === 0 || d === 1).toBe(true);   // 0 if tomorrow is a weekend day
  });
  it("counts only weekdays", () => {
    const d = new Date();
    d.setUTCDate(d.getUTCDate() + 14);
    const dte = bizDTE(d.toISOString().slice(0, 10));
    expect(dte).toBeGreaterThan(7);
    expect(dte).toBeLessThanOrEqual(11);
  });
});

describe("evalAlerts OICONF (overnight OI confirmation)", () => {
  const mk = (over) => ({
    under: "NVDA", type: "call", strike: 100, exp: "2099-01-08",
    score: 40, premium: 2e5, notional: 5e7, volOI: 1, dte: 10, _new: false, ...over,
  });
  it("fires on ≥30% overnight OI build with ≥$1M added notional, without _new", () => {
    const hits = evalAlerts([mk({ oiChg: { abs: 5000, pct: 0.5 } })]);
    expect(hits).toHaveLength(1);
    expect(hits[0].rule).toBe("OICONF");
    expect(hits[0].why).toMatch(/OI \+50% overnight/);
    expect(hits[0].ttl).toBeGreaterThan(3600e3);
  });
  it("skips small builds — pct below 30% or added notional below $1M", () => {
    expect(evalAlerts([mk({ oiChg: { abs: 5000, pct: 0.2 } })])).toEqual([]);
    // +80% but only 50 contracts on a $100 strike = $500k added notional
    expect(evalAlerts([mk({ oiChg: { abs: 50, pct: 0.8 } })])).toEqual([]);
  });
  it("caps at the top 5 by overnight % build, strongest first", () => {
    const rows = Array.from({ length: 8 }, (_, i) =>
      mk({ strike: 100 + i, oiChg: { abs: 5000, pct: 0.31 + i * 0.1 } }));
    const hits = evalAlerts(rows);
    expect(hits).toHaveLength(5);
    expect(hits[0].oiChgPct).toBeCloseTo(1.01);
    expect(hits.every((h) => h.rule === "OICONF")).toBe(true);
  });
  it("a row cut from the top-5 OICONF slots still fires its one-shot intraday rule", () => {
    const rows = Array.from({ length: 6 }, (_, i) =>
      mk({ strike: 100 + i, oiChg: { abs: 5000, pct: 0.9 - i * 0.1 } }));
    rows[5]._new = true; rows[5].score = 95;   // weakest OI build (rank 6) but hot new flow
    const hits = evalAlerts(rows);
    expect(hits).toHaveLength(6);
    expect(hits.filter((h) => h.rule === "OICONF")).toHaveLength(5);
    expect(hits.find((h) => h.strike === 105)?.rule).toBe("SCORE");   // not swallowed
  });
  it("wins over SCORE on the same row (one alert per row) and can be disabled", () => {
    const row = mk({ _new: true, score: 95, oiChg: { abs: 5000, pct: 0.5 } });
    expect(evalAlerts([row])[0].rule).toBe("OICONF");
    const off = evalAlerts([row], { enabled: { score: true, oiconf: false } });
    expect(off).toHaveLength(1);
    expect(off[0].rule).toBe("SCORE");
  });
  it("intraday rules carry a plain-English why", () => {
    const [hit] = evalAlerts([mk({ _new: true, score: 93, volOI: 5.2, premium: 1.2e6 })]);
    expect(hit.rule).toBe("SCORE");
    expect(hit.why).toMatch(/score 93/);
    expect(hit.why).toMatch(/5.2× OI/);
  });
});

describe("evalAlerts ΔOI hygiene parity (server: services/oi_hygiene.py)", () => {
  const mk = (over) => ({
    under: "NVDA", type: "call", strike: 100, exp: "2099-01-08",
    score: 40, premium: 2e5, notional: 5e7, volOI: 1, dte: 10, _new: false, ...over,
  });
  it("rollover-tagged OI pops never fire OICONF (migration ≠ new flow)", () => {
    const hits = evalAlerts([mk({ oiChg: { abs: 5000, pct: 0.5, tag: { rollover: true, expiring: false, earnings: null } } })]);
    expect(hits).toEqual([]);
  });
  it("expiring-tagged rows never fire OICONF", () => {
    const hits = evalAlerts([mk({ oiChg: { abs: 5000, pct: 0.9, tag: { expiring: true, rollover: false, earnings: null } } })]);
    expect(hits).toEqual([]);
  });
  it("earnings-tagged OICONF still fires (never-remove) with the ambiguity suffix", () => {
    const [hit] = evalAlerts([mk({ oiChg: { abs: 5000, pct: 0.5, tag: { expiring: false, rollover: false, earnings: { days_to: 2 } } } })]);
    expect(hit.rule).toBe("OICONF");
    expect(hit.why).toContain("earnings in 2 session(s) — direction ambiguous");
  });
  it("untagged rows behave exactly as before (no suffix, no suppression)", () => {
    const [hit] = evalAlerts([mk({ oiChg: { abs: 5000, pct: 0.5 } })]);
    expect(hit.why).not.toContain("[");
  });
});

describe("streakOf (multi-day persistence)", () => {
  // 2026-07-06 = Monday; all base dates are weekdays.
  const day = (date, total_vol) => ({ date, total_vol });
  const base = [day("2026-07-06", 100), day("2026-07-07", 110), day("2026-07-08", 90), day("2026-07-09", 100)];
  it("counts consecutive most-recent days ≥ mult × prior-day median", () => {
    const days = [...base, day("2026-07-10", 400), day("2026-07-13", 380)];
    const st = streakOf(days, { today: "2026-07-14" });
    expect(st.n).toBe(2);
    expect(st.median).toBe(105);   // median over ALL six prior days (spike days included)
  });
  it("a below-threshold TODAY is skipped, not a streak-breaker (partial day)", () => {
    const days = [...base, day("2026-07-10", 400), day("2026-07-13", 380), day("2026-07-14", 5)];
    expect(streakOf(days, { today: "2026-07-14" }).n).toBe(2);
  });
  it("an above-threshold TODAY joins the streak", () => {
    const days = [...base, day("2026-07-13", 400), day("2026-07-14", 500)];
    expect(streakOf(days, { today: "2026-07-14" }).n).toBe(2);
  });
  it("a missing day (ticker fell out of the scan = quiet day) BREAKS the streak", () => {
    // Mon 07-13 spike, Tue-Wed absent, Thu 07-16 spike → two isolated spikes, not \"2 straight days\"
    const days = [...base, day("2026-07-13", 400), day("2026-07-16", 380)];
    expect(streakOf(days, { today: "2026-07-17" }).n).toBe(1);
  });
  it("weekday-holiday stale duplicates are dropped before streak math", () => {
    // Fri 07-10 spike; Mon 07-13 records the identical stale row (holiday-style dup)
    const days = [...base, { date: "2026-07-10", total_vol: 400, call_vol: 240, put_vol: 160 },
      { date: "2026-07-13", total_vol: 400, call_vol: 240, put_vol: 160 }];
    expect(streakOf(days, { today: "2026-07-14" }).n).toBe(1);
  });
  it("needs minDays of prior history and a nonzero median", () => {
    expect(streakOf(base.slice(0, 3), { today: "2026-07-14" })).toBeNull();
    expect(streakOf([day("2026-07-06", 0), day("2026-07-07", 0), day("2026-07-08", 0), day("2026-07-09", 0)], { today: "2026-07-14" })).toBeNull();
  });
  it("quiet recent days mean streak 0", () => {
    const days = [...base, day("2026-07-13", 95)];
    expect(streakOf(days, { today: "2026-07-14" }).n).toBe(0);
  });
  it("weekend rows (stale Friday duplicates) neither count nor break the streak", () => {
    const days = [...base, day("2026-07-10", 400), day("2026-07-11", 400), day("2026-07-12", 400)];
    expect(streakOf(days, { today: "2026-07-13" }).n).toBe(1);   // Friday only
    expect(isTradingDay("2026-07-11")).toBe(false);              // Saturday
    expect(isTradingDay("2026-07-13")).toBe(true);               // Monday
  });
});

describe("evalTickerAlerts (SIGMA + FOLLOW)", () => {
  const roll = [{ under: "NVDA", callVol: 105000, putVol: 35000, maxScore: 71 }];
  const baselines = { NVDA: { avg: 40000, std: 15000, days: 6 } };
  it("SIGMA fires at ≥6σ above the ticker's baseline with a label + long ttl", () => {
    const hits = evalTickerAlerts(roll, baselines, {});
    expect(hits).toHaveLength(1);
    expect(hits[0].rule).toBe("SIGMA");
    expect(hits[0].key).toBe("sigma|NVDA");
    expect(hits[0].label).toMatch(/6.7σ above its 6-day baseline/);
    expect(hits[0].ttl).toBe(4 * 3600e3);
  });
  it("stays quiet below the sigma threshold or without a baseline", () => {
    expect(evalTickerAlerts([{ under: "NVDA", callVol: 40000, putVol: 20000 }], baselines, {})).toEqual([]);
    expect(evalTickerAlerts(roll, {}, {})).toEqual([]);
  });
  it("FOLLOW fires on a ≥2-day streak", () => {
    const hits = evalTickerAlerts(roll, {}, { NVDA: { n: 3, mult: 1.5, median: 40000 } });
    expect(hits).toHaveLength(1);
    expect(hits[0].rule).toBe("FOLLOW");
    expect(hits[0].label).toMatch(/3 straight days/);
  });
  it("ignores any legacy allow opt and respects enabled flags", () => {
    const streaks = { NVDA: { n: 2, mult: 1.5, median: 40000 } };
    expect(evalTickerAlerts(roll, baselines, streaks, { allow: ["SPY"] })).toHaveLength(2);   // allow ignored: whole market
    const only = evalTickerAlerts(roll, baselines, streaks, { enabled: { sigma: false, follow: true } });
    expect(only.map((h) => h.rule)).toEqual(["FOLLOW"]);
  });
});

describe("elapsedClock", () => {
  it("returns \u2014 for null/undefined/negative/non-finite", () => {
    expect(elapsedClock(null)).toBe("\u2014");
    expect(elapsedClock(undefined)).toBe("\u2014");
    expect(elapsedClock(-1)).toBe("\u2014");
    expect(elapsedClock(NaN)).toBe("\u2014");
  });
  it("formats in seconds when age < 60", () => {
    expect(elapsedClock(0)).toBe("0s");
    expect(elapsedClock(7)).toBe("7s");
    expect(elapsedClock(59.4)).toBe("59s");   // Math.round
  });
  it("switches to minutes at 60s", () => {
    expect(elapsedClock(60)).toBe("1m");
    expect(elapsedClock(125)).toBe("2m");
  });
  it("switches to hours at 60m", () => {
    expect(elapsedClock(60 * 60)).toBe("1h");
    expect(elapsedClock(125 * 60)).toBe("2h");
  });
});

describe("pulseState", () => {
  it("ERRORED beats stale+retry (precedence)", () => {
    const p = pulseState({ hasError: true, stale: true, retry: 30 });
    expect(p.dot).toBe("r");
    expect(p.label).toBe("ERRORED");
    expect(p.tier).toBe("err");
  });
  it("STALE retry Ns when stale with a retry window", () => {
    const p = pulseState({ stale: true, retry: 47 });
    expect(p.dot).toBe("r");
    expect(p.label).toBe("STALE \u00b7retry 47s");
    expect(p.tier).toBe("err");
  });
  it("STALE alone falls to warning tier", () => {
    expect(pulseState({ stale: true }).dot).toBe("y");
    expect(pulseState({ stale: true }).tier).toBe("warn");
  });
  it("LOADING when no mode and no data yet", () => {
    const p = pulseState({ mode: null, hasData: false });
    expect(p.dot).toBe("y");
    expect(p.label).toBe("LOADING");
  });
  it("FALLBACK on local universe scan", () => {
    const p = pulseState({ mode: "fallback", hasData: true });
    expect(p.dot).toBe("y");
    expect(p.label).toBe("FALLBACK");
  });
  it("LIVE (green/fresh) when market mode and age <= 30s", () => {
    const p = pulseState({ mode: "market", age: 12 });
    expect(p.dot).toBe("g");
    expect(p.label).toBe("LIVE");
    expect(p.tier).toBe("fresh");
  });
  it("LIVE slow (yellow/warn) between 30s and 90s", () => {
    const p = pulseState({ mode: "market", age: 65 });
    expect(p.dot).toBe("y");
    expect(p.label).toBe("LIVE \u00b7slow");
  });
  it("LIVE Hm when age is minutes/hours", () => {
    const p = pulseState({ mode: "market", age: 2500 });
    expect(p.dot).toBe("y");
    expect(p.label).toBe("LIVE \u00b742m");
  });
});

describe("formatFOLLOWStrip", () => {
  it("returns [] for empty / null / non-object input", () => {
    expect(formatFOLLOWStrip({})).toEqual([]);
    expect(formatFOLLOWStrip(null)).toEqual([]);
    expect(formatFOLLOWStrip(undefined)).toEqual([]);
  });
  it("drops sub-2 / NaN / zero streaks so a malformed map can\u0027t leak", () => {
    const out = formatFOLLOWStrip({
      AAPL: { n: 1, mult: 1.5 },
      NVDA: { n: 0, mult: 1.5 },
      TSLA: { n: NaN, mult: 1.5 },
      MSFT: { n: 2, mult: 1.5, median: 40000 },
    });
    expect(out).toHaveLength(1);
    expect(out[0].under).toBe("MSFT");
  });
  it("sorts by streak days desc, then mult desc, then ticker ASC", () => {
    const out = formatFOLLOWStrip({
      NVDA: { n: 3, mult: 1.5, median: 40000 },
      TSLA: { n: 5, mult: 1.5, median: 10000 },
      AMD:  { n: 5, mult: 2.0, median: 20000 },
      AAPL: { n: 2, mult: 1.5, median: 30000 },
    });
    expect(out.map((e) => e.under)).toEqual(["AMD", "TSLA", "NVDA", "AAPL"]);
  });
  it("clips to top-N (default 6, custom, zero, huge)", () => {
    const obj = {};
    for (let i = 0; i < 10; i++) obj[`T${i}`] = { n: 2, mult: 1.5, median: 1000 };
    expect(formatFOLLOWStrip(obj)).toHaveLength(6);
    expect(formatFOLLOWStrip(obj, { top: 3 })).toHaveLength(3);
    expect(formatFOLLOWStrip(obj, { top: 0 })).toHaveLength(0);
    expect(formatFOLLOWStrip(obj, { top: 100 })).toHaveLength(10);
  });
});

describe("tierOf", () => {
  it("OICONF is always high (overnight OI confirms yesterday's flow)", () => {
    expect(tierOf({ rule: "OICONF", score: 50 })).toBe("high");
    expect(tierOf({ rule: "OICONF", sigma: 2 })).toBe("high");
  });
  it("WHALE is always high (premium size)", () => {
    expect(tierOf({ rule: "WHALE", score: 30, premium: 10e6 })).toBe("high");
  });
  it("FOLLOW≥3 straight days is high; <3 is med (default followDays=2 is med)", () => {
    expect(tierOf({ rule: "FOLLOW", streak: 1 })).toBe("med");
    expect(tierOf({ rule: "FOLLOW", streak: 2 })).toBe("med");
    expect(tierOf({ rule: "FOLLOW", streak: 3 })).toBe("high");
    expect(tierOf({ rule: "FOLLOW", streak: 5 })).toBe("high");
  });
  it("SIGMA needs ≥5σ for high (4-5σ + 1 notch above the 4-σ rule floor)", () => {
    expect(tierOf({ rule: "SIGMA", sigma: 4 })).toBe("med");
    expect(tierOf({ rule: "SIGMA", sigma: 5 })).toBe("high");
    expect(tierOf({ rule: "SIGMA", sigma: 7.2 })).toBe("high");
  });
  it("SCORE needs ≥minScoreForFire (default 90) for high; lower floors respected", () => {
    expect(tierOf({ rule: "SCORE", score: 89 })).toBe("med");
    expect(tierOf({ rule: "SCORE", score: 90 })).toBe("high");
    expect(tierOf({ rule: "SCORE", score: 87 }, { minScoreForFire: 85 })).toBe("high");
    expect(tierOf({ rule: "SCORE", score: 84 }, { minScoreForFire: 85 })).toBe("med");
  });
  it("0DTE is med (too noisy for the sticky banner)", () => {
    expect(tierOf({ rule: "0DTE", score: 99 })).toBe("med");
  });
  it("null / undefined / no-rule → \"off\"", () => {
    expect(tierOf(null)).toBe("off");
    expect(tierOf(undefined)).toBe("off");
    expect(tierOf({})).toBe("off");
  });
});

describe("selectFires", () => {
  const baseT = 1_700_000_000_000;
  const mk = (over) => ({
    key: `k_${over.rule || "x"}_${over.under || "Y"}`, ckey: "ckey", t: baseT,
    time: "00:00:00", rule: over.rule, under: over.under || "NVDA", type: "call",
    strike: 100, exp: "2099-01-08",
    ...over,
  });

  it("returns [] for null / empty / only-meds", () => {
    expect(selectFires([])).toEqual([]);
    expect(selectFires(null)).toEqual([]);
    expect(selectFires([mk({ rule: "0DTE", score: 99 })])).toEqual([]);
  });
  it("includes only high-tier fires", () => {
    const log = [
      mk({ rule: "0DTE", score: 99 }),
      mk({ rule: "SCORE", score: 80 }),
      mk({ rule: "SCORE", score: 95 }),
      mk({ rule: "OICONF" }),
    ];
    expect(selectFires(log, { now: baseT }).map((h) => h.rule)).toEqual(["OICONF", "SCORE"]);
  });
  it("respects per-rule enabled toggle", () => {
    const log = [mk({ rule: "WHALE" }), mk({ rule: "OICONF" })];
    const out = selectFires(log, { now: baseT, enabled: { whale: false, oiconf: true } });
    expect(out.map((h) => h.rule)).toEqual(["OICONF"]);
  });
  it("ignores any legacy allow opt (universe fully open)", () => {
    const log = [mk({ under: "NVDA", rule: "OICONF" }), mk({ under: "QQQ", rule: "OICONF" })];
    expect(selectFires(log, { now: baseT, allow: ["NVDA"] }).map((h) => h.under)).toEqual(["NVDA", "QQQ"]);
  });
  it("drops entries older than ttlMs (defensive; alertLog usually pre-trims)", () => {
    const log = [mk({ rule: "OICONF", t: baseT - 90_000 })];
    expect(selectFires(log, { now: baseT, ttlMs: 60_000 })).toEqual([]);
  });
  it("drops acked keys (Set or plain-object form)", () => {
    const log = [mk({ rule: "OICONF", key: "oiconf|X" })];
    expect(selectFires(log, { now: baseT, acked: new Set(["oiconf|X"]) })).toEqual([]);
    expect(selectFires(log, { now: baseT, acked: { "score|Y": 1 } })).toHaveLength(1);
  });
  it("sorts by priority OICONF > WHALE > FOLLOW > SIGMA > SCORE", () => {
    const log = [
      mk({ rule: "SCORE", score: 95 }),
      mk({ rule: "SIGMA", sigma: 7 }),
      mk({ rule: "OICONF" }),
      mk({ rule: "WHALE" }),
    ];
    expect(selectFires(log, { now: baseT }).map((h) => h.rule)).toEqual(["OICONF", "WHALE", "SIGMA", "SCORE"]);
  });
  it("ties on rule are broken by t desc (newest wins)", () => {
    const log = [
      mk({ rule: "WHALE", t: baseT - 1000 }),
      mk({ rule: "WHALE", t: baseT }),
    ];
    expect(selectFires(log, { now: baseT }).map((h) => h.t)).toEqual([baseT, baseT - 1000]);
  });
  it("annotates _tier=\"high\" on returned hits so the JSX can rely on it", () => {
    const out = selectFires([mk({ rule: "OICONF" })], { now: baseT });
    expect(out[0]._tier).toBe("high");
  });
});

describe("pickBanner", () => {
  const mk = (rule) => ({ rule, key: `k_${rule}`, under: "NVDA", t: Date.now() });
  it("returns null on no fires", () => {
    expect(pickBanner([])).toBeNull();
    expect(pickBanner(null)).toBeNull();
  });
  it("returns the first sorted fire (precedence already applied by selectFires)", () => {
    expect(pickBanner([mk("SCORE"), mk("OICONF")]).rule).toBe("OICONF");
    expect(pickBanner([mk("WHALE")]).rule).toBe("WHALE");
  });
  it("returns the only fire when one qualifies", () => {
    expect(pickBanner([mk("FOLLOW")]).rule).toBe("FOLLOW");
  });
});

describe("evalAlerts noise pass (2026-09-02)", () => {
  const mk = (over = {}) => ({
    under: "SPY", type: "call", strike: 745, exp: "2099-01-08",
    score: 90, premium: 2e6, notional: 5e7, volOI: 3, dte: 5, _new: true, ...over,
  });
  it("enabled.scoreMin overrides the legacy minScore default (92 > 85)", () => {
    // No explicit minScore — the tightened default must come from enabled.scoreMin.
    const hits = evalAlerts([mk({ score: 88 })], { enabled: { score: true, scoreMin: 92 } });
    expect(hits).toHaveLength(0);
    const hits2 = evalAlerts([mk({ score: 93 })], { enabled: { score: true, scoreMin: 92 } });
    expect(hits2).toHaveLength(1);
  });
  it("enabled.whaleMin overrides the legacy whalePremium default ($25M)", () => {
    const hits = evalAlerts([mk({ score: 40, premium: 12e6 })], { enabled: { whale: true, whaleMin: 25e6 } });
    expect(hits).toHaveLength(0);
    const hits2 = evalAlerts([mk({ score: 40, premium: 26e6 })], { enabled: { whale: true, whaleMin: 25e6 } });
    expect(hits2[0].rule).toBe("WHALE");
  });
  it("perTickerCap keeps the strongest claims per ticker, priority SCORE > WHALE > 0DTE", () => {
    const rows = [
      mk({ under: "SPY", strike: 700, score: 95, premium: 1e6 }),                       // SCORE #1
      mk({ under: "SPY", strike: 705, score: 93, premium: 1e6 }),                       // SCORE #2
      mk({ under: "SPY", strike: 710, score: 91, premium: 30e6 }),                      // WHALE — cap hit
      mk({ under: "QQQ", strike: 500, score: 90, premium: 1e6 }),                       // other ticker untouched
    ];
    const hits = evalAlerts(rows, { perTickerCap: 2, enabled: { score: true, scoreMin: 85, whale: true, whaleMin: 25e6 } });
    const spy = hits.filter((h) => h.under === "SPY");
    expect(spy).toHaveLength(2);
    expect(spy.map((h) => h.strike).sort()).toEqual([700, 705]);   // strongest scores kept
    expect(hits.some((h) => h.under === "QQQ")).toBe(true);
  });
  it("perTickerCap=0 disables the cap (old behavior)", () => {
    const rows = [mk({ strike: 700 }), mk({ strike: 705 }), mk({ strike: 710 })];
    const hits = evalAlerts(rows, { perTickerCap: 0, enabled: { score: true, scoreMin: 85 } });
    expect(hits).toHaveLength(3);
  });
  it("side gate filters intraday rules by contract side, OICONF exempt", () => {
    const rows = [mk({ type: "put", score: 95 }), mk({ type: "call", score: 95 })];
    const callsOnly = evalAlerts(rows, { side: "call", enabled: { score: true, scoreMin: 85 } });
    expect(callsOnly).toHaveLength(1);
    expect(callsOnly[0].type).toBe("call");
    expect(evalAlerts(rows, { side: "all", enabled: { score: true, scoreMin: 85 } })).toHaveLength(2);
  });
});

describe("evalTickerAlerts noise pass (2026-09-02)", () => {
  const rollup = (under, vol) => [{ under, callVol: vol / 2, putVol: vol / 2, prem: 0, callPrem: 0, putPrem: 0, count: 1, maxScore: 90 }];
  const baseline = { avg: 8000, std: 4000, days: 5 };
  it("enabled.sigmaMin overrides the legacy sigmaMin default (6 > 4)", () => {
    // vol 36000 → σ = (36000-8000)/4000 = 7.0
    const hit7 = evalTickerAlerts(rollup("SPY", 36000), { SPY: baseline }, {}, { enabled: { sigma: true, sigmaMin: 6 } });
    expect(hit7).toHaveLength(1);
    const hit5 = evalTickerAlerts(rollup("SPY", 28000), { SPY: baseline }, {}, { enabled: { sigma: true, sigmaMin: 6 } });
    expect(hit5).toHaveLength(0);   // σ = 5.0 — passed the old 4σ gate, fails 6σ
  });
  it("enabled.followMin overrides the legacy followDays default (3 > 2)", () => {
    const streaks = { SPY: { n: 2, mult: 1.5, median: 10000, thr: 15000 } };
    expect(evalTickerAlerts(rollup("SPY", 36000), {}, streaks, { enabled: { follow: true, followMin: 3 } })).toHaveLength(0);
    streaks.SPY.n = 3;
    expect(evalTickerAlerts(rollup("SPY", 36000), {}, streaks, { enabled: { follow: true, followMin: 3 } })).toHaveLength(1);
  });
});

describe("W1 tracer — spreadPosition", () => {
  it("maps bid->0, mid->0.5, ask->1, clamps outside", () => {
    expect(spreadPosition(4, 4.2, 4)).toMatchObject({ pos: 0, state: "OK", side: "BID" });
    expect(spreadPosition(4, 4.2, 4.1).pos).toBeCloseTo(0.5, 5);
    expect(spreadPosition(4, 4.2, 4.2)).toMatchObject({ pos: 1, state: "OK", side: "ASK" });
    expect(spreadPosition(4, 4.2, 9).pos).toBe(1);
    expect(spreadPosition(4, 4.2, 1).pos).toBe(0);
  });
  it("NO_QUOTE on missing/zero, LOCKED on crossed (ask<=bid)", () => {
    expect(spreadPosition(null, 4.2, 4.1).state).toBe("NO_QUOTE");
    expect(spreadPosition(4, null, 4.1).state).toBe("NO_QUOTE");
    expect(spreadPosition(4, 4.2, null).state).toBe("NO_QUOTE");
    expect(spreadPosition(0, 0, 5).state).toBe("NO_QUOTE");
    expect(spreadPosition(4.2, 4, 4.1).state).toBe("LOCKED");
    expect(spreadPosition(4.2, 4, 4.1).side).toBe("LOCKED");
  });
  it("BID/MID/ASK exact, clamp edges, side label", () => {
    expect(spreadPosition(4, 4.2, 4).side).toBe("BID");
    expect(spreadPosition(4, 4.2, 4.1).side).toBe("MID");
    expect(spreadPosition(4, 4.2, 4.2).side).toBe("ASK");
    // boundary: pos<=0.33 → BID, pos>=0.67 → ASK — use clearly interior values
    expect(spreadPosition(4, 4.6, 4.15).side).toBe("BID"); // (4.15-4)/0.6 = 0.25
    expect(spreadPosition(4, 4.6, 4.45).side).toBe("ASK"); // (4.45-4)/0.6 = 0.75
    // near-boundary: 0.33 BID, 0.67 ASK (with tolerance)
    expect(spreadPosition(4, 4.6, 4.19).side).toBe("BID"); // (4.19-4)/0.6 ≈ 0.316
    expect(spreadPosition(4, 4.6, 4.42).side).toBe("ASK"); // (4.42-4)/0.6 = 0.70
  });
});

describe("W1 tracer — overviewStats", () => {
  const r = (type, side, premium) => ({ type, side, premium });
  it("rolls bull/bear legs, FIR, P/C, lean per H1", () => {
    const s = overviewStats([
      r("call", "ASK", 100000), r("call", "ASK", 50000),
      r("put", "BID", 30000), r("put", "ASK", 20000),
    ]);
    // bull = 100k+50k calls ASK + 30k puts BID = 180k; bear = 20k puts ASK
    expect(s.bullPrem).toBe(180000);
    expect(s.bearPrem).toBe(20000);
    expect(s.netPrem).toBe(160000);
    expect(s.fir).toBeCloseTo(0.8, 5);
    expect(s.pc).toBeCloseTo(50000 / 150000, 5);
    expect(s.lean).toBe("Bullish");
    expect(s.n).toBe(4);
    expect(s.rvol).toBeNull();
  });
  it("Neutral below FIR 0.3; empty tape is Neutral zeros", () => {
    const s = overviewStats([r("call", "ASK", 100), r("put", "ASK", 90)]);
    expect(s.fir).toBeCloseTo(10 / 190, 5);
    expect(s.lean).toBe("Neutral");
    const e = overviewStats([]);
    expect(e).toMatchObject({ bullPrem: 0, bearPrem: 0, netPrem: 0, fir: 0, lean: "Neutral", n: 0 });
  });
});

describe("W6 filter depth — equityType/signedOtm/isOpexDay", () => {
  it("classifies tickers without a vendor", () => {
    expect(equityType("SPY")).toBe("ETF");
    expect(equityType("QQQ")).toBe("ETF");
    expect(equityType("SPX")).toBe("INDEX");
    expect(equityType("VIX")).toBe("INDEX");
    expect(equityType("NVDA")).toBe("STOCK");
    expect(equityType("tsla")).toBe("STOCK");
    expect(equityType(null)).toBe("STOCK");
  });
  it("signed moneyness orients by type", () => {
    expect(signedOtm("call", 460, 450)).toBeCloseTo(10 / 450, 5);
    expect(signedOtm("call", 440, 450)).toBeCloseTo(-10 / 450, 5);
    expect(signedOtm("put", 440, 450)).toBeCloseTo(10 / 450, 5);
    expect(signedOtm("put", 460, 450)).toBeCloseTo(-10 / 450, 5);
    expect(signedOtm("call", 460, null)).toBeNull();
  });
  it("OPEX is the third Friday", () => {
    expect(isOpexDay("2026-09-18")).toBe(true);   // third Friday Sep 2026
    expect(isOpexDay("2026-09-11")).toBe(false);  // second Friday
    expect(isOpexDay("2026-09-19")).toBe(false);  // Saturday
    expect(isOpexDay("junk")).toBe(false);
  });
});

describe("W3-partial highlighting — highlightState", () => {
  it("BURST beats VOL_OI; VOL_OI needs volOI>=1; else NONE", () => {
    expect(highlightState({ volDelta: 1500, volOI: 3, oi: 1000 })).toBe("BURST");
    expect(highlightState({ volDelta: 10, volOI: 2.5, oi: 1000 })).toBe("VOL_OI");
    expect(highlightState({ volDelta: 0, volOI: 0.5, oi: 1000 })).toBe("NONE");
    expect(highlightState({ volDelta: 5000, volOI: 9, oi: 0 })).toBe("VOL_OI");
    expect(highlightState({})).toBe("NONE");
  });
});

describe("W2 strategy-leg port — flagSpreadLegs", () => {
  const leg = (ticker, type, strike, volume, exp = "2026-09-18") =>
    ({ ticker, type, strike, expiration: exp, volume });
  it("flags verticals on matched volumes, ignores the rest", () => {
    const rows = [leg("SPY", "call", 450, 2000), leg("SPY", "call", 455, 2100), leg("SPY", "call", 460, 50)];
    expect(flagSpreadLegs(rows)).toBe(2);
    expect(rows[0]._strat).toBe("VERT?");
    expect(rows[1]._strat).toBe("VERT?");
    expect(rows[2]._strat).toBeUndefined();
  });
  it("flags straddles within 5% strikes, respects the 1000 floor", () => {
    const rows = [leg("SPY", "call", 450, 3000), leg("SPY", "put", 445, 2900)];
    expect(flagSpreadLegs(rows)).toBe(2);
    expect(rows[0]._strat).toBe("STRADDLE?");
    const small = [leg("SPY", "call", 450, 500), leg("SPY", "put", 445, 480)];
    expect(flagSpreadLegs(small)).toBe(0);
  });
});

describe("Wave-2 SHIP engine — skew/pin/inventory", () => {
  const c = (type, delta, iv, strike = 450, oi = 1000) => ({ type, delta, iv, strike, oi });
  it("interpDeltaIV hits exact, interpolates, refuses extrapolation", () => {
    const rows = [c("put", -0.1, 0.30), c("put", -0.3, 0.40)];
    expect(interpDeltaIV(rows, -0.1, "put")).toBeCloseTo(0.30, 6);
    expect(interpDeltaIV(rows, -0.2, "put")).toBeCloseTo(0.35, 6);
    expect(interpDeltaIV(rows, -0.5, "put")).toBeNull();
    expect(interpDeltaIV([c("put", -0.2, 0.3)], -0.2, "put")).toBeNull();
  });
  it("skewLevels matches XZZ/C-W/Yan/convexity definitions", () => {
    const rows = [
      c("put", -0.2, 0.40), c("put", -0.5, 0.30), c("put", -0.8, 0.50),
      c("call", 0.3, 0.22), c("call", 0.5, 0.20),
    ];
    const s = skewLevels(rows);
    expect(s.smirk).toBeCloseTo(0.20, 6);
    expect(s.cwSpread).toBeCloseTo(-0.10, 6);
    expect(s.yanSlope).toBeCloseTo(0.10, 6);
    expect(s.convexity).toBeCloseTo(0.50, 6);
  });
  it("pinRisk finds max-OI strike, concentration, distance", () => {
    const rows = [c("call", 0.5, 0.2, 450, 5000), c("put", -0.5, 0.3, 450, 3000), c("call", 0.5, 0.2, 460, 1000), c("put", -0.5, 0.3, 440, 1000), c("call", 0.5, 0.2, 470, 1000)];
    const p = pinRisk(rows, 452);
    expect(p.maxOiStrike).toBe(450);
    expect(p.concentration).toBeCloseTo(10000 / 11000, 6);
    expect(p.distPct).toBeCloseTo(((450 - 452) / 452) * 100, 6);
    expect(pinRisk([], 452)).toBeNull();
  });
  it("quoteSkew spreads always, direction only vs prevMid", () => {
    const q = quoteSkew(1.0, 1.2);
    expect(q.tag).toBe("LEVEL");
    expect(q.relSpread).toBeCloseTo(0.2 / 1.1, 6);
    expect(quoteSkew(1.0, 1.2, 1.0).tag).toBe("UP");
    expect(quoteSkew(1.0, 1.2, 1.2).tag).toBe("DOWN");
    expect(quoteSkew(1.0, 1.2, 1.1).tag).toBe("FLAT");
    expect(quoteSkew(0, 0).tag).toBe("NOQUOTE");
    expect(quoteSkew(1.2, 1.0).tag).toBe("NOQUOTE");
  });
  it("midDrift returns pct over window, null when unusable", () => {
    expect(midDrift([100, 101, 102]).driftPct).toBeCloseTo(2, 6);
    expect(midDrift([100, 101, 102]).n).toBe(3);
    expect(midDrift([100])).toBeNull();
  });
});

describe("stampPollDeltas — per-poll stamping", () => {
  const s = (vol, mid) => ({ ticker: "SPY", type: "call", strike: 450, expiration: "2026-09-18", volume: vol, mid });
  it("first sighting: delta 0, prevMid null; second poll: delta + prior mid", () => {
    const v = new Map(), m = new Map();
    const p1 = [s(100, 4.1)];
    stampPollDeltas(p1, v, m);
    expect(p1[0]._volDelta).toBe(0);
    expect(p1[0]._prevMid).toBeNull();
    const p2 = [s(150, 4.2)];
    stampPollDeltas(p2, v, m);
    expect(p2[0]._volDelta).toBe(50);
    expect(p2[0]._prevMid).toBeCloseTo(4.1, 6);
  });
  it("volume reset reads as unknown (0), mid map keeps last good", () => {
    const v = new Map(), m = new Map();
    stampPollDeltas([s(500, 4.2)], v, m);
    const p2 = [s(10, null)];
    stampPollDeltas(p2, v, m);
    expect(p2[0]._volDelta).toBe(0);
    expect(p2[0]._prevMid).toBeCloseTo(4.2, 6);
  });
});

describe("nearestExpiryPin — Friday gate + nearest expiry", () => {
  const r = (ticker, strike, oi, exp, spot = 452) => ({ ticker, strike, oi, expiration: exp, spot });
  const MON = new Date("2026-08-31T12:00:00").getTime(); // Monday
  const FRI = new Date("2026-09-04T12:00:00").getTime(); // Friday
  it("index names eligible any day; picks nearest expiry", () => {
    const rows = [r("SPY", 450, 8000, "2026-09-18"), r("SPY", 450, 1000, "2026-09-18"), r("SPY", 455, 9000, "2026-09-25")];
    const p = nearestExpiryPin(rows, "SPY", MON);
    expect(p.eligible).toBe(true);
    expect(p.exp).toBe("2026-09-18");
    expect(p.maxOiStrike).toBe(450);
  });
  it("single names gated to Friday", () => {
    const rows = [r("NVDA", 180, 5000, "2026-09-18", 182)];
    expect(nearestExpiryPin(rows, "NVDA", MON)).toEqual({ eligible: false, reason: "Fri-only" });
    const fri = nearestExpiryPin(rows, "NVDA", FRI);
    expect(fri.eligible).toBe(true);
    expect(fri.maxOiStrike).toBe(180);
  });
  it("null on empty or ticker mismatch", () => {
    expect(nearestExpiryPin([], "SPY", MON)).toBeNull();
    expect(nearestExpiryPin([r("SPY", 450, 100, "2026-09-18")], "QQQ", MON)).toBeNull();
  });
});

describe("rollSpread — Roll 1984 bounce estimator", () => {
  it("recovers known spread from synthetic bounce", () => {
    const px = [100, 101, 100, 101, 100, 101, 100, 101, 100]; // 8 even deltas
    const r = rollSpread(px);
    expect(r.truncated).toBe(false);
    expect(r.spread).toBeCloseTo(2, 6);
    expect(r.n).toBe(9);
  });
  it("truncates flat and trending series to 0", () => {
    expect(rollSpread([5, 5, 5, 5, 5]).truncated).toBe(true);
    expect(rollSpread([5, 5, 5, 5, 5]).spread).toBe(0);
    expect(rollSpread([1, 2, 3, 4, 5, 6]).truncated).toBe(true);
  });
  it("needs 3+ mids; pushCapped bounds the ring", () => {
    expect(rollSpread([1, 2]).spread).toBeNull();
    const r = pushCapped(pushCapped([1, 2], 3, 3), 4, 3);
    expect(r).toEqual([2, 3, 4]);
  });
});

describe("rollPooled — expiry-bucket cost", () => {
  const bounce = (n, lo = 4, hi = 4.2) => Array.from({ length: n }, (_, i) => (i % 2 === 0 ? lo : hi));
  it("pools two bounce rings into one spread", () => {
    const r = rollPooled([bounce(20), bounce(20)]);
    expect(r.building).toBe(false);
    expect(r.spread).toBeCloseTo(0.4, 1); // full bounce amplitude ± joint noise
  });
  it("building state under 30 deltas, never a number", () => {
    const r = rollPooled([bounce(10)]);
    expect(r.building).toBe(true);
    expect(r.spread).toBeNull();
  });
});

describe("poll-chain integration — the effect's exact sequence", () => {
  it("poll2 arrows + deltas; pool exits building at 30 deltas", () => {
    const prevVol = new Map(), prevMid = new Map(), rings = new Map();
    const mk = (vol, a, b) => ([
      { ticker: "SPY", type: "call", strike: 450, expiration: "2026-09-18", volume: vol, mid: a },
      { ticker: "SPY", type: "put", strike: 445, expiration: "2026-09-18", volume: vol, mid: b },
    ]);
    let arrows, deltas;
    for (let p = 0; p < 16; p++) {
      const batch = mk(100 + p * 10, 4.1 + p * 0.01, 4.0 - p * 0.005);
      stampPollDeltas(batch, prevVol, prevMid);
      for (const s of batch) {
        rings.set(contractKey(s), pushCapped(rings.get(contractKey(s)), Number(s.mid), 60));
      }
      if (p === 1) {
        arrows = batch.map((s) => quoteSkew(4.0, 4.3, s._prevMid).tag);
        deltas = batch.map((s) => s._volDelta);
      }
    }
    expect(arrows).toEqual(["UP", "UP"]);
    expect(deltas).toEqual([10, 10]);
    const pool = rollPooled([...rings.values()]);
    expect(pool.building).toBe(false);
    // steady drift = positive autocov = textbook truncation, not a bug.
    expect(pool.truncated).toBe(true);
    expect(pool.spread).toBe(0);
  });
});

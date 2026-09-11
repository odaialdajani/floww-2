// tideFeed.test.js — pure helper contracts for Tidehunter Pro v3.
import {
  parseAlert, parseFeedAlerts, isContextual, isDirectional, stageOf,
  formatMovePct, targetTravelPct, directionOf, tradeNowOf, feedBodyOf,
  verdictWithheld, scanFreshness, oiHeldLabel, moneynessPct, applyScreenToScans,
  applyScreenToAlerts, testCondition, matchCustomScan, BUILTIN_SCREENS,
  TRADE_NOW_FLOOR, SCAN_FACTS,
} from "./tideFeed";

const dirAlert = (over = {}) => ({
  key: "oiconf|NVDA|call|182.5|2026-09-19",
  rule: "OICONF", tier: "GOLD", conviction: 94, bias: "BULLISH",
  under: "NVDA", type: "call", strike: 182.5, exp: "2026-09-19", dte: 14,
  score: 94, premium: 18400000, under_price: 178.4, move_pct: 1.8, asof_ts: new Date().toISOString(),
  key_levels_json: JSON.stringify({ entry: 178.4, invalidation: 173.94, target: 188.21 }),
  context_json: JSON.stringify({
    activity_summary: "Call print: 218,000 contracts",
    institutional_indicators: ["Top-decile composite score"],
    market_regime: "NEGATIVE_GAMMA",
    dealer_positioning: "Net short gamma",
  }),
  why: "OI +41% held overnight",
  ...over,
});
const sigmaAlert = (over = {}) => ({
  key: "sigma|SPY", rule: "SIGMA", tier: "SILVER", conviction: 79,
  bias: "BEARISH", under: "SPY", type: null, strike: null, exp: null,
  sigma: 4.6, move_pct: null, asof_ts: new Date().toISOString(),
  key_levels_json: null, context_json: null, why: "volume 4.6σ",
  ...over,
});

describe("parseAlert — key_levels_json + context_json (never parsed before)", () => {
  it("parses both JSON blobs", () => {
    const a = parseAlert(dirAlert());
    expect(a.levels).toEqual({ entry: 178.4, invalidation: 173.94, target: 188.21 });
    expect(a.context.activity_summary).toMatch(/218,000/);
    expect(a.context.institutional_indicators).toEqual(["Top-decile composite score"]);
  });
  it("survives null / malformed JSON", () => {
    const a = parseAlert(sigmaAlert({ key_levels_json: "{oops", context_json: "" }));
    expect(a.levels).toBeNull();
    expect(a.context).toBeNull();
  });
  it("accepts already-parsed objects", () => {
    const a = parseAlert(dirAlert({ key_levels_json: { entry: 1, invalidation: 0.9, target: 1.1 } }));
    expect(a.levels.entry).toBe(1);
  });
  it("maps arrays", () => {
    expect(parseFeedAlerts([dirAlert(), sigmaAlert()])).toHaveLength(2);
  });
});

describe("contextual vs directional rows", () => {
  it("null bias or null strike (SIGMA/STRATEGY/SOURCE) is contextual", () => {
    expect(isContextual(sigmaAlert())).toBe(true);
    expect(isContextual(dirAlert({ bias: null }))).toBe(true);
    expect(isContextual(dirAlert({ bias: null, strike: 100 }))).toBe(true);
    expect(isDirectional(sigmaAlert())).toBe(false);
  });
  it("bias + strike is directional", () => {
    expect(isDirectional(dirAlert())).toBe(true);
    expect(isContextual(dirAlert())).toBe(false);
  });
});

describe("stageOf", () => {
  it("Early = fresh print, Building = FOLLOW/SIGMA, Confirmed = OICONF", () => {
    expect(stageOf(dirAlert({ rule: "OICONF" }))).toEqual({ label: "Confirmed", n: 3 });
    expect(stageOf(dirAlert({ rule: "FOLLOW" }))).toEqual({ label: "Building", n: 2 });
    expect(stageOf(sigmaAlert())).toEqual({ label: "Building", n: 2 });
    expect(stageOf(dirAlert({ rule: "SCORE" }))).toEqual({ label: "Early", n: 1 });
    expect(stageOf(dirAlert({ rule: "WHALE" }))).toEqual({ label: "Early", n: 1 });
  });
});

describe("formatMovePct — move_pct is already a percent, never ×100", () => {
  it("renders +0.8% for move_pct 0.8 (the old *100 bug showed +80.00%)", () => {
    expect(formatMovePct(0.8)).toBe("+0.8%");
  });
  it("signs negatives and handles null", () => {
    expect(formatMovePct(-1.25)).toBe("-1.3%");
    expect(formatMovePct(0)).toBe("+0.0%");
    expect(formatMovePct(null)).toBe("—");
  });
});

describe("targetTravelPct", () => {
  it("is move_pct ÷ target distance", () => {
    // (188.21-178.40)/178.40 = 5.5% target distance; 1.8/5.5 ≈ 33%
    expect(targetTravelPct(parseAlert(dirAlert()))).toBe(33);
  });
  it("null without levels or move", () => {
    expect(targetTravelPct(sigmaAlert())).toBeNull();
    expect(targetTravelPct(parseAlert(dirAlert({ move_pct: null })))).toBeNull();
  });
});

describe("directionOf", () => {
  it("always pairs arrow with word", () => {
    expect(directionOf(dirAlert())).toEqual({ arrow: "▲", word: "BULLISH", cls: "bull" });
    expect(directionOf(sigmaAlert())).toEqual({ arrow: "▼", word: "BEARISH", cls: "bear" });
    expect(directionOf(dirAlert({ bias: null })).word).toBe("NO DIRECTION");
  });
});

describe("tradeNowOf / feedBodyOf", () => {
  const low = dirAlert({ key: "score|x", rule: "SCORE", conviction: 68, under: "SPY", strike: 642 });
  it("picks the top directional row ≥ floor", () => {
    expect(tradeNowOf([sigmaAlert(), low, dirAlert()]).key).toBe(dirAlert().key);
  });
  it("withholds below the floor", () => {
    expect(tradeNowOf([sigmaAlert(), low])).toBeNull();
    expect(tradeNowOf([sigmaAlert()])).toBeNull();
  });
  it("excludes the pinned row from the body (never drawn twice)", () => {
    const tn = tradeNowOf([low, dirAlert()]);
    const body = feedBodyOf([low, dirAlert()], tn);
    expect(body.map((a) => a.key)).toEqual([low.key]);
  });
  it(`floor is ${TRADE_NOW_FLOOR}`, () => {
    expect(TRADE_NOW_FLOOR).toBe(75);
  });
});

describe("verdictWithheld", () => {
  it("withholds when stale && cache_age > 2×scan_ttl", () => {
    expect(verdictWithheld({ stale: true, age: 130, ttl: 60 })).toBe(true);
    expect(verdictWithheld({ stale: true, age: 60, ttl: 60 })).toBe(false);
    expect(verdictWithheld({ stale: false, age: 9999, ttl: 60 })).toBe(false);
  });
});

describe("oiHeldLabel / moneynessPct", () => {
  it("held vs faded", () => {
    expect(oiHeldLabel(0.41)).toBe("held");
    expect(oiHeldLabel(-0.08)).toBe("faded");
    expect(oiHeldLabel(null)).toBe("— no prior day");
  });
  it("moneyness as signed %", () => {
    expect(moneynessPct(178.4, 182.5)).toBe("-2.2%");
    expect(moneynessPct(null, 100)).toBeNull();
  });
});

const scanRow = (over = {}) => ({
  under: "NVDA", type: "call", strike: 182.5, exp: "2026-09-19", vol: 218000,
  oi: 100000, iv: 0.38, delta: 0.4, regime: "negative", volOI: 2.9,
  notional: 1e9, dte: 14, premium: 18.4e6, score: 94, ftype: "sweep",
  arch: "FRESH", oiChgPct: 0.41, ...over,
});

describe("built-in screens filter AND rank", () => {
  const rows = [
    scanRow(),
    scanRow({ under: "SPY", type: "put", dte: 1, premium: 12e6, score: 91, arch: "WHALE", oiChgPct: 0.22 }),
    scanRow({ under: "AAPL", type: "put", dte: 42, premium: 2e5, score: 63, arch: "HEDGE", oiChgPct: 0.06 }),
  ];
  it("seven built-ins exist", () => {
    expect(BUILTIN_SCREENS.map((s) => s.id)).toEqual(
      ["all", "whale", "oiconf", "zerodte", "hedge", "fresh", "mine"],
    );
  });
  it("whale keeps premium size, oiconf keeps ΔOI builds", () => {
    const whale = BUILTIN_SCREENS.find((s) => s.id === "whale");
    expect(applyScreenToScans(rows, whale, {}).map((r) => r.under).sort()).toEqual(["NVDA", "SPY"]);
    const oi = BUILTIN_SCREENS.find((s) => s.id === "oiconf");
    expect(applyScreenToScans(rows, oi, {}).map((r) => r.under).sort()).toEqual(["NVDA", "SPY"]);
  });
  it("mine scopes to the universe", () => {
    const mine = BUILTIN_SCREENS.find((s) => s.id === "mine");
    expect(applyScreenToScans(rows, mine, { universe: ["AAPL"] }).map((r) => r.under)).toEqual(["AAPL"]);
  });
  it("alert screens cohere with the feed", () => {
    const whale = BUILTIN_SCREENS.find((s) => s.id === "whale");
    const out = applyScreenToAlerts([dirAlert(), sigmaAlert()], whale, {});
    expect(out.map((a) => a.under)).toEqual(["NVDA"]);
  });
});

describe("rule builder over the 17 facts + 4 ticker facts", () => {
  it("SCAN_FACTS is 18 mkScanRow keys + oiChgPct − deltaEst − spot", () => {
    expect(SCAN_FACTS).toHaveLength(17);
    expect(SCAN_FACTS).toContain("oiChgPct");
    expect(SCAN_FACTS).not.toContain("deltaEst");
    expect(SCAN_FACTS).not.toContain("spot");
  });
  it("conditions AND together (≥/≤/between/is)", () => {
    const r = scanRow();
    expect(testCondition(r, { fact: "score", op: "≥", value: "70" })).toBe(true);
    expect(testCondition(r, { fact: "score", op: "≤", value: "70" })).toBe(false);
    expect(testCondition(r, { fact: "dte", op: "between", value: "7,21" })).toBe(true);
    expect(testCondition(r, { fact: "type", op: "is", value: "call" })).toBe(true);
    expect(testCondition(r, { fact: "type", op: "is", value: "put" })).toBe(false);
  });
  it("ticker facts resolve from context", () => {
    expect(testCondition(scanRow(), { fact: "streak", op: "≥", value: "3" }, { streak: 4 })).toBe(true);
    expect(testCondition(scanRow(), { fact: "streak", op: "≥", value: "3" }, {})).toBe(false);
  });
  it("matchCustomScan requires a matching fired rule instead of a price proxy", () => {
    expect(matchCustomScan(scanRow(), { rule: "WHALE", conditions: [] }, {})).toBe(false);
    expect(matchCustomScan(scanRow(), { rule: "0DTE", conditions: [] }, {})).toBe(false);
    expect(matchCustomScan(scanRow(), { rule: "OICONF", conditions: [] }, {})).toBe(false);
    expect(matchCustomScan(scanRow(), { rule: "SCORE", conditions: [] }, {})).toBe(false);
    expect(matchCustomScan(scanRow(), { rule: "SCORE", conditions: [] }, {}, [{...scanRow(), rule:"SCORE"}])).toBe(true);
    expect(matchCustomScan(scanRow({ score: 50 }), { rule: "ANY", conditions: [{ fact: "score", op: "≥", value: "70" }] }, {})).toBe(false);
  });
});


describe("shared screen safety",()=>{
 it("uses entered percent values for open-interest rules without changing stored fractions",()=>{
  const row=scanRow({oiChgPct:0.2});
  expect(testCondition(row,{fact:"oiChgPct",op:"≥",value:"20"})).toBe(true);
  expect(testCondition(row,{fact:"oiChgPct",op:"≥",value:"21"})).toBe(false);
  expect(testCondition(row,{fact:"oiChgPct",op:"between",value:"19,21"})).toBe(true);
  expect(row.oiChgPct).toBe(0.2);
  expect(testCondition(scanRow({oiChgPct:0.29}),{fact:"oiChgPct",op:"≥",value:"29"})).toBe(true);
  expect(testCondition(scanRow({oiChgPct:-0.12}),{fact:"oiChgPct",op:"between",value:"-20,-5"})).toBe(true);
  expect(testCondition(row,{fact:"oiChgPct",op:"≥",value:""})).toBe(false);
 });
 it("ages unchanged scans even when the server stale flag is false",()=>{
  const received=100000;
  expect(scanFreshness({mode:"market",age:5,received,ttl:60},received+116000).status).toBe("STALE");
  expect(scanFreshness({mode:"market",age:5,received,ttl:60},received+110000).status).toBe("AVAILABLE");
  expect(scanFreshness({mode:"market",age:null,received},received).status).toBe("AGE UNKNOWN");
 });
 it("withholds old and incomplete trade-now candidates",()=>{
  expect(tradeNowOf([dirAlert({asof_ts:"2020-01-01T00:00:00Z"})])).toBeNull();
  expect(tradeNowOf([dirAlert({bias:"UNKNOWN"})])).toBeNull();
  expect(tradeNowOf([dirAlert({type:null})])).toBeNull();
 });
 it("applies custom conditions and copied built-ins to both sections",()=>{
  const custom={custom:true,rule:"ANY",conditions:[{fact:"under",op:"is",value:"NVDA"}]};
  expect(applyScreenToAlerts([dirAlert(),dirAlert({under:"SPY"})],custom,{})).toHaveLength(1);
  const copy={custom:true,copyOf:"mine",rule:"ANY",conditions:[]};
  expect(applyScreenToScans([scanRow()],copy,{universe:[]})).toHaveLength(0);
  expect(applyScreenToAlerts([dirAlert()],copy,{universe:[]})).toHaveLength(0);
 });
 it("evaluates OR groups without weakening outer AND conditions",()=>{
  const s={custom:true,conditions:[{fact:"score",op:"≥",value:70},{join:"OR",conditions:[{fact:"type",op:"is",value:"put"},{fact:"under",op:"is",value:"NVDA"}]}]};
  expect(matchCustomScan(scanRow(),s,{})).toBe(true);
  expect(matchCustomScan(scanRow({under:"SPY"}),s,{})).toBe(false);
 });
});

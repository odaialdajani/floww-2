/**
 * @jest-environment jsdom
 *
 * T1 ticker-universe contract (2026-09-07): one case-normalized,
 * order-preserving deduped list shared by buttons, count, arrows and search.
 * Static fixture: 95 raw entries -> 80 unique.
 */
import {
  normalizeTicker,
  dedupePreserveOrder,
  buildTickerUniverse,
  searchUniverse,
  stepIndex,
  fetchFullUniverse,
  RENDER_CAP,
} from "./tickerUniverse";

// Static fixture mirroring the /api/tickers shape: trinity (3) + default (17)
// + popular (75) = 95 raw with known duplicates -> 80 unique.
const TRINITY = ["^SPX", "SPY", "QQQ"];
const DEFAULT = ["SPY", "QQQ", "IWM", "DIA", "AAPL", "NVDA", "TSLA", "META", "AMZN", "MSFT", "AMD", "GOOGL", "RIVN", "RBLX", "HIMS", "IREN", "MU"];
const POPULAR = [
  "SPY", "QQQ", "IWM", "DIA", "AAPL", "NVDA", "TSLA", "META", "AMZN", "MSFT",
  "AMD", "GOOGL", "AVGO", "COST", "NFLX", "AMD", "PLTR", "SOFI", "HOOD", "COIN",
  "MSTR", "DKNG", "UBER", "ABNB", "SNOW", "DDOG", "NET", "CRWD", "ZS", "OKTA",
  "MDB", "NOW", "OSCR", "PATH", "UPS", "ZETA", "SPXW", "VTI", "VOO", "ARKK",
  "XLF", "XLE", "XLV", "JPM", "BAC", "WFC", "GS", "MS", "C", "AXP",
  "LLY", "UNH", "JNJ", "XOM", "CVX", "LIN", "NEE", "DUK", "SO", "AEP",
  "HD", "LOW", "TGT", "WMT", "PG", "KO", "PEP", "MRK", "PFE", "ABBV",
  "LITE", "RKLB", "VSAT", "APP", "IONQ",
];

test("static fixture is 95 raw entries", () => {
  expect(TRINITY.length + DEFAULT.length + POPULAR.length).toBe(95);
});

test("normalizeTicker uppercases, trims, strips leading $", () => {
  expect(normalizeTicker("  spy ")).toBe("SPY");
  expect(normalizeTicker("$qqq")).toBe("QQQ");
  expect(normalizeTicker("^SPX")).toBe("^SPX");
});

test("dedupe preserves first-seen order and normalizes case", () => {
  expect(dedupePreserveOrder(["SPY", "spy", "QQQ", "SPY", "hood"])).toEqual(["SPY", "QQQ", "HOOD"]);
});

test("fixture dedupes to 80 unique", () => {
  expect(dedupePreserveOrder([...TRINITY, ...DEFAULT, ...POPULAR]).length).toBe(80);
});

test("buildTickerUniverse accepts object, array, and null shapes", () => {
  const fromObj = buildTickerUniverse({ trinity: TRINITY, default: DEFAULT, popular: POPULAR });
  expect(fromObj.length).toBe(80);
  expect(fromObj.slice(0, 3)).toEqual(["^SPX", "SPY", "QQQ"]);
  // Plain array shape (legacy test call sites).
  expect(buildTickerUniverse(["SPY", "QQQ", "HOOD"])).toEqual(["SPY", "QQQ", "HOOD"]);
  // Null/empty yields empty; callers apply their own fallback sets.
  expect(buildTickerUniverse(null)).toEqual([]);
  expect(buildTickerUniverse({})).toEqual([]);
});

test("SPY -> QQQ -> next unique: no two-symbol dup loop", () => {
  const u = buildTickerUniverse({ trinity: TRINITY, default: DEFAULT, popular: POPULAR });
  expect(stepIndex(u, "SPY", 1)).toBe(u.indexOf("QQQ"));
  expect(u[stepIndex(u, "QQQ", 1)]).not.toBe("SPY");
  expect(u[stepIndex(u, "QQQ", 1)]).toBe("IWM");
});

test("boundaries wrap: last -> first, first -> last", () => {
  const u = ["SPY", "QQQ", "HOOD"];
  expect(u[stepIndex(u, "HOOD", 1)]).toBe("SPY");
  expect(u[stepIndex(u, "SPY", -1)]).toBe("HOOD");
});

test("unknown ticker wraps from the boundary (pinned contract)", () => {
  const u = ["SPY", "QQQ"];
  expect(u[stepIndex(u, "RIVN", 1)]).toBe("SPY");
  expect(u[stepIndex(u, "RIVN", -1)]).toBe("QQQ");
});

test("search filters before slicing: finds item past 500", () => {
  const big = Array.from({ length: 600 }, (_, i) => `T${String(i).padStart(4, "0")}`);
  const res = searchUniverse(big, "T0559", 12);
  expect(res.total).toBe(1);
  expect(res.matches).toEqual(["T0559"]);
});

test("search is case-insensitive and capped after filtering", () => {
  const big = Array.from({ length: 600 }, (_, i) => `SYM${i}`);
  const res = searchUniverse(big, "sym", 12);
  expect(res.total).toBe(600);
  expect(res.matches.length).toBe(12);
  expect(res.matches[0]).toBe("SYM0");
});

test("RENDER_CAP is 500", () => {
  expect(RENDER_CAP).toBe(500);
});

test("empty search exposes a capped default view, not the full universe", () => {
  const big = Array.from({ length: 600 }, (_, i) => `T${String(i).padStart(4, "0")}`);
  const res = searchUniverse(big, "", 12);
  expect(res.total).toBe(0);
  expect(res.matches).toEqual([]);
});

describe("fetchFullUniverse (T2 paged universe)", () => {
  const pagesOf = (lists) => {
    let i = 0;
    const calls = [];
    const get = async (url) => {
      calls.push(url);
      const batch = lists[Math.min(i, lists.length - 1)];
      const last = i >= lists.length - 1;
      i += 1;
      return { data: { tickers: batch, total: 6000, has_more: !last } };
    };
    return { get, calls };
  };

  test("walks pages until has_more is false", async () => {
    const { get, calls } = pagesOf([["A", "B"], ["C"]]);
    const out = await fetchFullUniverse(get, "http://x/api");
    expect(out.symbols).toEqual(["A", "B", "C"]);
    expect(calls).toHaveLength(2);
    expect(calls[0]).toContain("page=1");
    expect(calls[1]).toContain("page=2");
  });

  test("stops on transport failure, keeping fetched rows", async () => {
    const get = async (url) => {
      if (url.includes("page=1")) return { data: { tickers: ["A"], total: 99, has_more: true } };
      throw new Error("down");
    };
    const out = await fetchFullUniverse(get, "http://x/api");
    expect(out.symbols).toEqual(["A"]);
  });

  test("empty on total failure", async () => {
    const out = await fetchFullUniverse(async () => { throw new Error("down"); }, "http://x/api");
    expect(out.symbols).toEqual([]);
    expect(out.pages).toBe(0);
  });
});


test("provider catalogs larger than twelve thousand remain complete", async () => {
  const names = Array.from({ length: 13135 }, (_, i) => 'T' + i);
  const get = async url => {
    const page = Number(new URL(url).searchParams.get('page'));
    return { data: { tickers: names.slice((page - 1) * 5000, page * 5000), total: names.length,
      has_more: page * 5000 < names.length, complete_provider_catalog: true } };
  };
  const result = await fetchFullUniverse(get, 'http://x/api');
  expect(result.symbols).toEqual(names);
  expect(result.complete).toBe(true);
});

test("duplicates cannot masquerade as a complete directory", async () => {
  const result = await fetchFullUniverse(async () => ({ data: {
    tickers: ["SPY", "spy"], total: 2, has_more: false, complete_provider_catalog: true,
  } }), "http://x/api");
  expect(result.symbols).toEqual(["SPY"]);
  expect(result.complete).toBe(false);
});

test("an unverified completeness claim remains incomplete", async () => {
  const result = await fetchFullUniverse(async () => ({ data: {
    tickers: ["SPY"], total: 1, has_more: false,
  } }), "http://x/api");
  expect(result.complete).toBe(false);
});

test.each([
  { tickers: ["D"], total: 3, asof: "new" },
  { tickers: ["C", "D"], total: 4, asof: "new" },
  { tickers: ["D"], total: 3, asof: "old" },
])("directory changes during paging cannot hide a missing name", async lastPage => {
  const get = jest.fn()
    .mockResolvedValueOnce({ data: { tickers: ["A", "B"], total: 4, asof: "old", has_more: true, complete_provider_catalog: true } })
    .mockResolvedValueOnce({ data: { ...lastPage, has_more: false, complete_provider_catalog: true } });
  const result = await fetchFullUniverse(get, "http://x/api");
  expect(result.complete).toBe(false);
  expect(result.symbols).toEqual(["A", "B"]);
});

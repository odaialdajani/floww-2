import { isTradeClosed, tradePnl, tradeOutcome, strategyRiskReward, contractMid, legPrice, effectiveOptionPrice, formatNotional, ticketToJournalEntries, tradeIdeaToJournalEntries, JOURNAL_STORAGE_KEY, condorWidth } from "./tradeMath";

describe("isTradeClosed", () => {
  it("open when no exit date and no exit price", () => {
    expect(isTradeClosed({ exit_price: "", exit_date: "" })).toBe(false);
    expect(isTradeClosed({})).toBe(false);
  });
  it("closed at $0 total loss (the bug: exit_price 0 with an exit_date)", () => {
    expect(isTradeClosed({ exit_price: 0, exit_date: "2026-07-11" })).toBe(true);
    expect(isTradeClosed({ exit_price: "0", exit_date: "2026-07-11" })).toBe(true);
  });
  it("closed when exit price is set even without a date", () => {
    expect(isTradeClosed({ exit_price: "5.25", exit_date: "" })).toBe(true);
  });
});

describe("tradePnl", () => {
  it("long total loss = -entry*qty*100", () => {
    expect(tradePnl({ action: "buy", entry_price: "5", exit_price: 0, quantity: "10" })).toBe(-5000);
  });
  it("long winner", () => {
    expect(tradePnl({ action: "buy", entry_price: "2", exit_price: "5", quantity: "1" })).toBe(300);
  });
  it("short winner (credit kept)", () => {
    expect(tradePnl({ action: "sell", entry_price: "3", exit_price: "1", quantity: "1" })).toBe(200);
  });
});

describe("tradeOutcome", () => {
  it("scratch when exit == entry", () => {
    expect(tradeOutcome({ action: "buy", entry_price: "5", exit_price: "5" })).toBe("scratch");
  });
  it("win/loss by direction", () => {
    expect(tradeOutcome({ action: "buy", entry_price: "5", exit_price: "6" })).toBe("win");
    expect(tradeOutcome({ action: "buy", entry_price: "5", exit_price: "4" })).toBe("loss");
    expect(tradeOutcome({ action: "sell", entry_price: "5", exit_price: "4" })).toBe("win");
  });
  it("total loss is a loss, not scratch", () => {
    expect(tradeOutcome({ action: "buy", entry_price: "5", exit_price: 0 })).toBe("loss");
  });
});

describe("strategyRiskReward", () => {
  it("returns — for both when IV/price estimate is missing (no $NaN)", () => {
    const r = strategyRiskReward("buy_call", "—", 1, 100);
    expect(r).toEqual({ maxRisk: "—", maxReward: "—" });
    expect(r.maxRisk).not.toContain("NaN");
  });
  it("long call: defined risk (premium), unlimited reward", () => {
    const r = strategyRiskReward("buy_call", 5, 2, 100);
    expect(r.maxRisk).toBe("$1,000");           // 5 * 2 * 100
    expect(r.maxReward).toBe("Unlimited");
  });
  it("straddle is a LONG debit — defined risk, not 'Unlimited' risk", () => {
    const r = strategyRiskReward("straddle", 5, 1, 100);
    expect(r.maxRisk).toBe("$500");
    expect(r.maxReward).toBe("Unlimited");
  });
  it("iron condor is defined-risk both sides, never 'Unlimited'", () => {
    const r = strategyRiskReward("iron_condor", 2, 1, 100);
    expect(r.maxRisk).toBe("Defined");
    expect(r.maxReward).toBe("$200");
  });
  it("naked short call keeps unlimited risk", () => {
    const r = strategyRiskReward("sell_call", 3, 1, 100);
    expect(r.maxRisk).toBe("Unlimited");
    expect(r.maxReward).toBe("$300");
  });
});

describe("contractMid", () => {
  it("prefers mid of bid/ask", () => {
    expect(contractMid({ bid: 0.45, ask: 0.55 })).toBeCloseTo(0.5);
  });
  it("falls back to last when one-sided", () => {
    expect(contractMid({ bid: 0, ask: 0, last: 1.3 })).toBeCloseTo(1.3);
  });
  it("one-sided bid alone counts", () => {
    expect(contractMid({ bid: 2.0 })).toBeCloseTo(2.0);
  });
  it("NaN when nothing quoted", () => {
    expect(Number.isFinite(contractMid({}))).toBe(false);
  });
});

describe("effectiveOptionPrice (SOFI degraded-ticket regression)", () => {
  const sofi = { spot: 18.2, strike: 22, iv: null, delta: null, oi: null };
  it("no quote + no IV + no limit -> NaN (panel must gate Review)", () => {
    const r = effectiveOptionPrice(sofi, "buy_call", "");
    expect(Number.isFinite(r.price)).toBe(false);
    expect(r.source).toBe("none");
  });
  it("limit override rescues a quoteless strike", () => {
    const r = effectiveOptionPrice(sofi, "buy_call", "1.20");
    expect(r.price).toBeCloseTo(1.2);
    expect(r.source).toBe("limit");
  });
  it("live ASK beats IV estimate for buys (fills lift the offer)", () => {
    const sel = { spot: 18.2, iv: 0.55, call_bid: 0.45, call_ask: 0.55 };
    const r = effectiveOptionPrice(sel, "buy_call", "");
    expect(r.price).toBeCloseTo(0.55);
    expect(r.source).toBe("ask");
  });
  it("sells price off the BID", () => {
    const sel = { spot: 18.2, iv: 0.55, call_bid: 0.45, call_ask: 0.55 };
    const r = effectiveOptionPrice(sel, "sell_call", "");
    expect(r.price).toBeCloseTo(0.45);
    expect(r.source).toBe("bid");
  });
  it("straddle sums both leg ASKs (debit package)", () => {
    const sel = { spot: 100, call_bid: 1, call_ask: 1.2, put_bid: 0.9, put_ask: 1.1 };
    const r = effectiveOptionPrice(sel, "straddle", "");
    expect(r.price).toBeCloseTo(2.3);
    expect(r.source).toBe("ask-sum");
  });
  it("IV fallback when no quote (old behavior preserved)", () => {
    const r = effectiveOptionPrice({ spot: 100, iv: 0.2 }, "buy_call", "");
    expect(r.price).toBeCloseTo(0.2);
    expect(r.source).toBe("iv");
  });
});

describe("legPrice (executable side)", () => {
  it("buy prefers ask, sell prefers bid", () => {
    const sel = { call_bid: 1.0, call_ask: 1.2, call_last: 1.1 };
    expect(legPrice(sel, "call", "buy")).toEqual({ price: 1.2, source: "ask" });
    expect(legPrice(sel, "call", "sell")).toEqual({ price: 1.0, source: "bid" });
  });
  it("falls back to mid when executable side missing", () => {
    const sel = { call_bid: 1.0, call_ask: 0, call_last: 0 };
    expect(legPrice(sel, "call", "buy").source).toBe("mid");
  });
});

describe("iron condor wings", () => {
  const wings = { put_long: 745, put_short: 750, call_short: 760, call_long: 765, credit: 1.5 };
  it("condor prices off credit, never a single-leg guess", () => {
    const sel = { spot: 755, iv: 0.2, call_bid: 2, call_ask: 2.2 };
    expect(effectiveOptionPrice(sel, "iron_condor", "", wings)).toEqual({ price: 1.5, source: "credit" });
    expect(effectiveOptionPrice(sel, "iron_condor", "").source).toBe("none");
  });
  it("risk from narrowest wing minus credit", () => {
    expect(condorWidth(wings)).toBe(5);
    const r = strategyRiskReward("iron_condor", 1.5, 1, 755, wings);
    expect(r.maxRisk).toBe("$350");   // (5 - 1.5) * 100
    expect(r.maxReward).toBe("$150");
  });
  it("journal carries wing structure", () => {
    const [e] = ticketToJournalEntries({ ticker: "SPY", strike: 755, spot: 755, quantity: 1, effectivePrice: 1.5, strategy: "iron_condor", wings, timestamp: "2026-09-06T00:00:00.000Z" });
    expect(e.notes).toMatch(/745\/750/);
    expect(e.notes).toMatch(/760\/765/);
  });
});

describe("formatNotional", () => {
  it("never $0 on missing price (SOFI showed $0)", () => {
    expect(formatNotional(NaN, 1)).toBe("—");
    expect(formatNotional("—", 1)).toBe("—");
  });
  it("prices qty*100", () => {
    expect(formatNotional(1.2, 1)).toBe("$120");
  });
});

describe("ticketToJournalEntries (ticket must land in journal, any ticker)", () => {
  const base = { ticker: "SOFI", strike: 22, spot: 18.2, quantity: 1,
    effectivePrice: 1.2, expiry: "2026-09-18", timestamp: "2026-09-06T00:00:00.000Z" };
  it("buy_call -> single call/buy entry TradeJournal can render", () => {
    const [e] = ticketToJournalEntries({ ...base, strategy: "buy_call" });
    expect(e.ticker).toBe("SOFI");
    expect(e.type).toBe("call");
    expect(e.action).toBe("buy");
    expect(e.strike).toBe(22);
    expect(e.entry_price).toBe(1.2);
    expect(e.quantity).toBe("1"); // journal form shape (strings; tradePnl parses)
  });
  it("sell_put -> put/sell with credit", () => {
    const [e] = ticketToJournalEntries({ ...base, strategy: "sell_put" });
    expect(e.type).toBe("put");
    expect(e.action).toBe("sell");
  });
  it("multi-leg collapses to one entry with strategy in setup (no fabricated legs)", () => {
    const [e] = ticketToJournalEntries({ ...base, strategy: "straddle" });
    expect(e.setup).toMatch(/STRADDLE/);
    expect(e.entry_price).toBe(1.2);
  });
  it("missing price still journals (price unknown, never dropped)", () => {
    const entries = ticketToJournalEntries({ ...base, strategy: "buy_call", effectivePrice: NaN });
    expect(entries.length).toBe(1);
    expect(entries[0].entry_price).toBe("");
  });
  it("storage key matches TradeJournal/TradeAnalytics", () => {
    expect(JOURNAL_STORAGE_KEY).toBe("floww_trades_v2");
  });
});

describe("tradeIdeaToJournalEntries (issue #17: TradeEntry -> journal store)", () => {
  const idea = (over = {}) => ({
    template: "iron_condor",
    templateName: "Iron Condor",
    ticker: "spy",
    spot: 645.2,
    data: { put_short: 630, put_long: 625, call_short: 660, call_long: 665, contracts: 2, credit: 1.5 },
    regime: "positive_gamma",
    timestamp: "2026-09-06T12:00:00.000Z",
    ...over,
  });
  const journalKeys = ["ticker", "type", "action", "strike", "expiry", "quantity", "entry_price", "entry_date"];
  const hasJournalShape = (e) => journalKeys.every(k => k in e);

  it("iron_condor maps without loss: wings+credit in notes/setup, contracts->quantity, regime->gex_regime", () => {
    const [e] = tradeIdeaToJournalEntries(idea());
    expect(hasJournalShape(e)).toBe(true);
    expect(e.ticker).toBe("SPY");
    expect(e.quantity).toBe("2");
    expect(e.gex_regime).toBe("positive_gamma");
    expect(e.setup).toMatch(/IRON CONDOR/);
    expect(e.notes).toMatch(/625/); expect(e.notes).toMatch(/630/);
    expect(e.notes).toMatch(/660/); expect(e.notes).toMatch(/665/);
    expect(e.notes).toMatch(/1\.5/);
    expect(e.entry_price).toBe(1.5);
    expect(isTradeClosed(e)).toBe(false); // open idea, renders in journal open list
  });
  it("long_straddle sums premiums, no fabricated legs", () => {
    const [e] = tradeIdeaToJournalEntries(idea({
      template: "long_straddle", templateName: "Long Straddle",
      data: { strike: 645, contracts: 1, call_premium: 8.2, put_premium: 7.9 },
      regime: "negative_gamma",
    }));
    expect(e.type).toBe("call"); expect(e.action).toBe("buy");
    expect(e.strike).toBe(645);
    expect(e.entry_price).toBeCloseTo(16.1, 5);
    expect(e.setup).toMatch(/STRADDLE/);
    expect(e.notes).toMatch(/8\.2/); expect(e.notes).toMatch(/7\.9/);
    expect(e.gex_regime).toBe("negative_gamma");
  });
  it("call_spread keeps both strikes, debit as entry price", () => {
    const [e] = tradeIdeaToJournalEntries(idea({
      template: "call_spread", templateName: "Bull Call Spread",
      data: { long_strike: 645, short_strike: 660, contracts: 3, debit: 4.2 },
    }));
    expect(e.type).toBe("call"); expect(e.action).toBe("buy");
    expect(e.strike).toBe(645);
    expect(e.notes).toMatch(/660/); expect(e.notes).toMatch(/4\.2/);
    expect(e.entry_price).toBe(4.2);
    expect(e.quantity).toBe("3");
  });
  it("put_spread maps to put/buy with both strikes", () => {
    const [e] = tradeIdeaToJournalEntries(idea({
      template: "put_spread", templateName: "Bear Put Spread",
      data: { long_strike: 645, short_strike: 630, contracts: 1, debit: 3.1 },
    }));
    expect(e.type).toBe("put"); expect(e.action).toBe("buy");
    expect(e.strike).toBe(645);
    expect(e.notes).toMatch(/630/);
    expect(e.entry_price).toBe(3.1);
  });
  it("single_leg Buy Put -> put/buy; Sell Call -> call/sell", () => {
    const [b] = tradeIdeaToJournalEntries(idea({
      template: "single_leg", templateName: "Single Leg",
      data: { action: "Buy Put", strike: 640, contracts: 1, premium: 5.5 },
    }));
    expect(b.type).toBe("put"); expect(b.action).toBe("buy");
    expect(b.strike).toBe(640); expect(b.entry_price).toBe(5.5);
    const [s] = tradeIdeaToJournalEntries(idea({
      template: "single_leg", templateName: "Single Leg",
      data: { action: "Sell Call", strike: 670, contracts: 2, premium: 2.1 },
    }));
    expect(s.type).toBe("call"); expect(s.action).toBe("sell");
    expect(s.entry_price).toBe(2.1);
  });
  it("missing price still journals (never dropped), unknown template falls back without fabrication", () => {
    const [e] = tradeIdeaToJournalEntries(idea({
      template: "weird_new", templateName: "Weird",
      data: { contracts: 1 },
    }));
    expect(hasJournalShape(e)).toBe(true);
    expect(e.entry_price).toBe("");
    expect(e.setup).toMatch(/WEIRD_NEW/);
  });
  it("entries carry journal-compatible P&L math (short credit kept if closed at 0)", () => {
    const [e] = tradeIdeaToJournalEntries(idea());
    expect(isTradeClosed(e)).toBe(false); // open idea, no phantom close
    // sell entry at 1.5 x2: closed at 0 keeps the credit (normal short math, no NaN)
    expect(tradePnl({ ...e, exit_price: "0", exit_date: "2026-09-07" })).toBe(300);
  });
});

import { buildPaperOptionOrderRequest, resolvePaperOptionOrder } from "./paperOptionOrder";

const selection = {
  oi_symbol: "SPY261218P00500000",
  call_bid: 1.1,
  call_ask: 1.3,
  put_bid: 1.2,
  put_ask: 1.5,
};

describe("resolvePaperOptionOrder", () => {
  test.each([
    ["buy_call", "buy", "call", 1.3, "ask"],
    ["buy_put", "buy", "put", 1.5, "ask"],
    ["sell_call", "sell", "call", 1.1, "bid"],
    ["sell_put", "sell", "put", 1.2, "bid"],
  ])("uses the executable side for %s", (strategy, side, optionType, price, priceSource) => {
    expect(resolvePaperOptionOrder({ strategy, selection, limitPrice: "" })).toMatchObject({
      side, optionType, limitPrice: price, priceSource, orderType: "limit",
    });
  });

  test("accepts a positive explicit limit when no quote exists", () => {
    expect(resolvePaperOptionOrder({ strategy: "buy_put", selection: {}, limitPrice: "0.75" })).toMatchObject({
      limitPrice: 0.75, priceSource: "limit", orderType: "limit",
    });
  });

  test.each(["0", "-1", "NaN"])("rejects invalid entered limit %s instead of falling back", (limitPrice) => {
    expect(resolvePaperOptionOrder({ strategy: "buy_call", selection, limitPrice })).toBeNull();
  });

  test.each(["straddle", "iron_condor"])("refuses single-symbol %s tickets", (strategy) => {
    expect(resolvePaperOptionOrder({ strategy, selection, limitPrice: "2.5" })).toBeNull();
  });

  test("refuses IV, mid, last, missing, zero, and negative execution prices", () => {
    expect(resolvePaperOptionOrder({ strategy: "buy_call", selection: { ...selection, call_ask: 0 }, limitPrice: "" })).toBeNull();
    expect(resolvePaperOptionOrder({ strategy: "buy_call", selection: { call_last: 2 }, limitPrice: "" })).toBeNull();
    expect(resolvePaperOptionOrder({ strategy: "buy_call", selection: { iv: 0.2, spot: 100 }, limitPrice: "" })).toBeNull();
  });
});

describe("buildPaperOptionOrderRequest", () => {
  const ticket = {
    strategy: "buy_put", oi_symbol: selection.oi_symbol, ticker: "SPY", strike: 500, expiry: "2026-12-18", quantity: 2,
    orderType: "limit", orderSide: "buy", optionType: "put",
    orderLimitPrice: 1.5, priceSource: "ask", put_ask: 1.5,
  };

  test("builds a strictly positive limit request with correct side", () => {
    expect(buildPaperOptionOrderRequest(ticket)).toEqual({
      symbol: selection.oi_symbol, qty: "2", side: "buy", order_type: "limit", limit_price: "1.5",
    });
  });

  test.each([
    [{ ...ticket, strategy: "straddle" }],
    [{ ...ticket, strategy: "iron_condor" }],
    [{ ...ticket, orderType: "market" }],
    [{ ...ticket, orderLimitPrice: 0 }],
    [{ ...ticket, orderLimitPrice: -1 }],
    [{ ...ticket, orderSide: "sell" }],
    [{ ...ticket, optionType: "call" }],
    [{ ...ticket, priceSource: "last" }],
    [{ ...ticket, put_ask: 1.4 }],
    [{ ...ticket, quantity: 0 }],
    [{ ...ticket, oi_symbol: "SPY261218C00500000" }],
    [{ ...ticket, ticker: "QQQ" }],
    [{ ...ticket, strike: 501 }],
    [{ ...ticket, expiry: "2026-12-19" }],
    [{ ...ticket, expiry: undefined }],
    [{ ...ticket, oi_symbol: "not-an-osi-symbol" }],
  ])("refuses unsafe request payload %j", (badTicket) => {
    expect(buildPaperOptionOrderRequest(badTicket)).toBeNull();
  });

  test("uses the explicit positive limit, never a zero-price fallback", () => {
    expect(buildPaperOptionOrderRequest({
      ...ticket, orderLimitPrice: 0.8, limitPrice: 0.8, priceSource: "limit",
    }).limit_price).toBe("0.8");
  });
});

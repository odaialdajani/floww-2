import { journalDateKey, journalKeysEqual } from "./TradeJournal";

describe("journalDateKey", () => {
  it("truncates ISO timestamps to date part", () => {
    expect(journalDateKey("2026-09-06T14:22:10")).toBe("2026-09-06");
    expect(journalDateKey("2026-09-06")).toBe("2026-09-06");
    expect(journalDateKey(null)).toBe("");
    expect(journalDateKey(undefined)).toBe("");
  });
});

describe("journalKeysEqual", () => {
  const local = { ticker: "SPY", type: "call", action: "buy", strike: 755, expiry: "", entry_date: "2026-09-06" };
  it("matches server ISO row to local date-only row (the systematic dupe)", () => {
    const server = { ...local, entry_date: "2026-09-06T14:22:10", expiry: "2026-09-18T00:00:00" };
    const local2 = { ...local, expiry: "2026-09-18" };
    expect(journalKeysEqual(local2, server)).toBe(true);
  });
  it("keeps distinct-day tickets apart", () => {
    expect(journalKeysEqual(local, { ...local, entry_date: "2026-09-05" })).toBe(false);
  });
  it("ticker compare is case/caret insensitive", () => {
    expect(journalKeysEqual({ ...local, ticker: "^spy" }, local)).toBe(true);
  });
  it("keeps separate broker orders even at the same time", () => {
    expect(journalKeysEqual({ ...local, broker_order_id: "order-one" },
      { ...local, broker_order_id: "order-two" })).toBe(false);
  });
  it("does not merge a broker fill into a matching manual ticket", () => {
    const fill = { ...local, broker_order_id: "order-one" };
    expect(journalKeysEqual(local, fill)).toBe(false);
    expect(journalKeysEqual(fill, local)).toBe(false);
  });
  it("recognizes a reloaded fill with the same broker identity", () => {
    const fill = { ...local, broker_order_id: "order-one" };
    expect(journalKeysEqual(fill, { ...fill, entry_date: "2026-09-06T14:22:10" })).toBe(true);
  });
  it("keeps one broker holding when its unknown fill time becomes known", () => {
    const fill = { ...local, broker_order_id: "order-one", entry_date: "" };
    expect(journalKeysEqual(fill, { ...fill, entry_date: "2026-09-06T14:22:10" })).toBe(true);
  });
});

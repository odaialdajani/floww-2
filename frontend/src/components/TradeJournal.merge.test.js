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
});

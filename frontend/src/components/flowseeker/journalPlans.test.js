import { persistJournalSeeds } from "./journalPlans";
beforeEach(() => localStorage.clear());
test("saves a manual draft once without a broker call", () => {
 const seed = { ticker: "SPY", contract_id: "SPY260918P00600000", entry_date: "2026-09-11", source: "tidehunter-manual" };
 expect(persistJournalSeeds([seed, seed])).toBe(1);
 expect(persistJournalSeeds([seed])).toBe(0);
 const rows = JSON.parse(localStorage.getItem("floww_trades_v2"));
 expect(rows).toHaveLength(1);
 expect(rows[0]).toMatchObject({ source: "tidehunter-manual", status: "draft" });
});
test("refuses to overwrite damaged saved work", () => {
 localStorage.setItem("floww_trades_v2", "broken");
 expect(() => persistJournalSeeds([{ ticker: "SPY" }])).toThrow();
 expect(localStorage.getItem("floww_trades_v2")).toBe("broken");
});

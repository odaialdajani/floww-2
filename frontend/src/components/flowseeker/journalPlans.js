// Local drafts only. This module has no network or broker capabilities.
const KEY = "floww_trades_v2";
const keyOf = s => [s.ticker, s.contract_id || s.osi || "", s.type, s.action,
  s.strike ?? "", s.expiry ?? "", s.entry_date ?? ""].join("|");
export function persistJournalSeeds(seeds) {
 const raw = localStorage.getItem(KEY);
 const existing = raw == null ? [] : JSON.parse(raw);
 if (!Array.isArray(existing)) throw new Error("Saved journal could not be read");
 const seen = new Set(existing.map(keyOf));
 const fresh = [];
 for (const seed of seeds || []) {
  if (!seed?.ticker || seen.has(keyOf(seed))) continue;
  seen.add(keyOf(seed));
  fresh.push({ ...seed, id: globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`,
   created_at: new Date().toISOString(), source: seed.source || "tidehunter-manual", status: "draft" });
 }
 if (fresh.length) localStorage.setItem(KEY, JSON.stringify([...fresh, ...existing]));
 return fresh.length;
}

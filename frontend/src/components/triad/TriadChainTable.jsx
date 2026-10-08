import React, { useMemo } from "react";

/**
 * TriadChainTable — strike-grouped contract table from chain endpoint rows.
 *
 * One row per strike: call bid/ask + delta on the left, put bid/ask on the
 * right, strike center, Review selects the strike into the desk context.
 * Anything missing renders unknown ('—'/explicit), never fabricated; the
 * caption states fixture-vs-live provenance expectations. No order path:
 * Review selects, it never submits.
 */
const dash = value => (typeof value === "number" && Number.isFinite(value) ? value : "—");

export default function TriadChainTable({ rows, expiry, selectedStrike, onReview }) {
  const grouped = useMemo(() => {
    const byStrike = new Map();
    for (const row of rows || []) {
      if (!row || typeof row !== "object") continue;
      const strike = Number(row.strike);
      if (!Number.isFinite(strike)) continue;
      const type = String(row.type || row.opt_type || row.side || "").toLowerCase();
      const entry = byStrike.get(strike) || { strike };
      if (type.startsWith("call") || type === "c") entry.call = row;
      else if (type.startsWith("put") || type === "p") entry.put = row;
      byStrike.set(strike, entry);
    }
    return [...byStrike.values()].sort((a, b) => a.strike - b.strike);
  }, [rows]);

  if (!grouped.length) {
    return <p role="status">No listed contracts for this expiry in the chain response.</p>;
  }
  const spread = leg => (typeof leg?.bid === "number" && typeof leg?.ask === "number"
    ? (leg.ask - leg.bid).toFixed(2) : "—");
  return <div className="panel"><div className="panelhead">
    <strong>Exact contract review</strong><small>{expiry || "no expiry selected"}</small></div>
    <div className="table-wrap"><table className="contract-table">
      <thead><tr><th>Call bid / ask</th><th>Δ</th><th>Strike</th><th>Put bid / ask</th><th>Spread</th><th>Review</th></tr></thead>
      <tbody>{grouped.map(g => {
        const selected = g.strike === selectedStrike;
        return <tr key={g.strike} className={selected ? "selected" : ""}>
          <td>{dash(g.call?.bid)} / {dash(g.call?.ask)}</td>
          <td>{dash(g.call?.delta)}</td>
          <td>{g.strike}</td>
          <td>{dash(g.put?.bid)} / {dash(g.put?.ask)}</td>
          <td>{g.call ? spread(g.call) : spread(g.put)}</td>
          <td><button type="button" aria-label={`Review strike ${g.strike}`}
            onClick={() => onReview && onReview({ strike: g.strike, expiry })}>Review</button></td>
        </tr>;
      })}</tbody>
    </table></div>
    <div className="chart-caption">Vendor quotes and Greeks as returned · actual contract IDs and current broker timestamps are required before live review.</div>
  </div>;
}

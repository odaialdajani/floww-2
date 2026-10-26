import React, { useEffect, useMemo, useRef } from "react";

const number = value => typeof value === 'number' && Number.isFinite(value);
const dash = value => number(value) ? value : '—';
const sideOf = row => ({ call: 'call', c: 'call', ce: 'call', put: 'put', p: 'put', pe: 'put' })[
  String(row?.type || row?.opt_type || row?.side || '').toLowerCase()];
const rootOf = ticker => String(ticker || '').toUpperCase().replace(/^\^/, '');

// M2 G5 (Hermes-2, 2026-10-24): the priority row for the chain table — an
// existing selected strike wins; otherwise the nearest listed strike to a
// finite spot; nothing to prioritize without either. Pure on purpose: the
// choice is unit-pinned (TriadChainTable.priority.test.jsx) while the
// scroll-into-view behavior is measured in the real browser (jsdom scrollers
// are zero-height, so a scroll assertion there would be vacuous).
export function priorityStrike(grouped, spot, selectedStrike) {
  if (selectedStrike != null && (grouped || []).some(g => g.strike === selectedStrike)) return selectedStrike;
  const s = typeof spot === 'number' && Number.isFinite(spot) ? spot : null;
  if (s == null || !(grouped || []).length) return null;
  return grouped.reduce((best, g) => (Math.abs(g.strike - s) < Math.abs(best.strike - s) ? g : best), grouped[0]).strike;
}

// Identity admission only; never repair or recompute producer exposure.
// Repeated sides are ambiguous even when quotes match. Neither may win.
export function admitContracts(rows, ticker, expiry) {
  const buckets = new Map();
  let rejected = 0;
  for (const row of rows || []) {
    const side = sideOf(row);
    const osi = typeof row?.osi === 'string' ? row.osi.trim().toUpperCase() : '';
    const match = /^([A-Z][A-Z0-9.]{0,5})\s*(\d{6})([CP])(\d{8})$/.exec(osi);
    const root = rootOf(ticker);
    const roots = root === 'SPX' ? ['SPX', 'SPXW'] : [root];
    const expectedDate = typeof expiry === 'string' ? expiry.slice(2).replace(/-/g, '') : '';
    const identityValid = row && number(row.strike) && row.strike > 0 && side
      && row.expiry === expiry && (!row.ticker || rootOf(row.ticker) === root)
      && (!osi || (match && roots.includes(match[1]) && match[2] === expectedDate
        && match[3] === (side === 'call' ? 'C' : 'P')
        && Number(match[4]) === Math.round(row.strike * 1000)
        && Math.abs(row.strike * 1000 - Number(match[4])) < 0.000001));
    if (!identityValid) { rejected += 1; continue; }
    const key = `${row.strike}:${side}`;
    const bucket = buckets.get(key) || [];
    bucket.push({ ...row, type: side, osi });
    buckets.set(key, bucket);
  }
  const admitted = [];
  let duplicates = 0;
  for (const bucket of buckets.values()) {
    if (bucket.length !== 1) duplicates += bucket.length;
    else admitted.push(bucket[0]);
  }
  return { rows: admitted, rejected, duplicates, clean: rejected === 0 && duplicates === 0 };
}

export function ContractClocks({ row }) {
  return <small className="wall-desk-clocks">
    Bid observed {row?.bid_event_time || row?.bid_timestamp || 'unknown'} · Ask observed {row?.ask_event_time || row?.ask_timestamp || 'unknown'}
    {' · '}Receipt {row?.received_at || 'unknown'}
  </small>;
}

export default function TriadChainTable({ rows, ticker, expiry, spot = null, selectedStrike, onReview, onSelectContract }) {
  const admission = useMemo(() => admitContracts(rows, ticker, expiry), [rows, ticker, expiry]);
  const grouped = useMemo(() => {
    const byStrike = new Map();
    for (const row of admission.rows) {
      const entry = byStrike.get(row.strike) || { strike: row.strike };
      entry[row.type] = row;
      byStrike.set(row.strike, entry);
    }
    return [...byStrike.values()].sort((a, b) => a.strike - b.strike);
  }, [admission]);
  // M2 G5: prioritization preserves the strike ladder — the near-spot (or
  // selected) row is the one brought into view first, centered in the scroll
  // region; no row is reordered, removed or windowed, and every clock stays.
  const scrollRef = useRef(null);
  const priority = useMemo(() => priorityStrike(grouped, spot, selectedStrike), [grouped, spot, selectedStrike]);
  useEffect(() => {
    const region = scrollRef.current;
    if (!region || priority == null) return;
    const row = region.querySelector(`tr[data-strike="${priority}"]`);
    if (!row) return;
    const rowTop = row.getBoundingClientRect().top - region.getBoundingClientRect().top + region.scrollTop;
    const next = Math.max(0, rowTop - (region.clientHeight - row.offsetHeight) / 2);
    if (Math.abs(region.scrollTop - next) > 1) region.scrollTop = next;
  }, [priority, grouped]);
  const spread = leg => number(leg?.bid) && number(leg?.ask) && leg.bid >= 0 && leg.ask >= leg.bid
    ? (leg.ask - leg.bid).toFixed(2) : '—';
  const leg = (row, side) => <>
    <div>{dash(row?.bid)} / {dash(row?.ask)}</div>
    {row && <><ContractClocks row={row} />
      {row.osi ? <button type="button" aria-label={`Review ${side} ${row.osi}`}
        onClick={() => onSelectContract?.(row)}>{side === 'call' ? 'Call' : 'Put'} · {row.osi}</button>
        : <small>Exact contract ID unavailable</small>}
    </>}
  </>;
  return <div className="panel wall-desk-chain"><div className="panelhead">
    <strong>Exact contract review</strong><small>{expiry || 'no expiry selected'}</small></div>
    {!admission.clean && <p role="status">Contract identity unavailable for {admission.rejected + admission.duplicates} row(s): mismatched or duplicate identities withheld. Their exposure snapshot is unavailable.</p>}
    {!grouped.length ? <p role="status">No unambiguous listed contracts for this expiry in the chain response.</p>
      : <div className="wall-desk-table-scroll" role="region" aria-label="Contract comparison" tabIndex={0} ref={scrollRef}><table className="contract-table">
        <thead><tr><th>Call bid / ask</th><th>Call Δ</th><th>Call spread</th><th>Strike</th><th>Put bid / ask</th><th>Put Δ</th><th>Put spread</th><th>Focus</th></tr></thead>
        <tbody>{grouped.map(g => <tr key={g.strike} data-strike={g.strike} className={g.strike === selectedStrike ? 'selected' : ''}>
          <td>{leg(g.call, 'call')}</td><td>{dash(g.call?.delta)}</td><td>{spread(g.call)}</td>
          <td>{g.strike}</td><td>{leg(g.put, 'put')}</td><td>{dash(g.put?.delta)}</td><td>{spread(g.put)}</td>
          <td><button type="button" aria-label={`Review strike ${g.strike}`}
            onClick={() => onReview?.({ strike: g.strike, expiry })}>Focus strike</button></td>
        </tr>)}</tbody>
      </table></div>}
    <div className="chart-caption">Quotes and spreads are premium per share in USD; Δ is dimensionless. Spread is ask minus bid only for a finite, non-crossed quote. Missing clocks are unknown; receipt is not observation. Selecting a side reviews its exact ID and never submits an order.</div>
  </div>;
}

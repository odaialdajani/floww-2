import React from 'react';
import { fmtUSD } from '../scanLogic.js';

// Dark pool — honest: no side, no direction, no bullish/bearish. Only time/ticker/price/size/notional/sector/level/date.
export default function DarkPoolPanel({ prints, levels, state = 'ready', controls = {}, onControl }) {
  if (state === 'no_data' || state === 'paid_gate') {
    return <div data-testid="darkpool-paid-gate">Dark pool prints require a paid feed — no free real-time source. Showing FINRA context only.</div>;
  }
  if (state === 'loading') return <div data-testid="darkpool-loading">Loading dark pool…</div>;
  if (state === 'error') return <div data-testid="darkpool-error">Dark pool unavailable</div>;
  if (!prints || prints.length === 0) return <div data-testid="darkpool-empty">No prints in window</div>;

  return (
    <div data-testid="darkpool-panel">
      <div className="fsb-darkpool__controls" data-testid="darkpool-controls">
        <span>Top N: {[1,2,3,5].map((n) => <button key={n} data-testid={`darkpool-top-${n}`} onClick={() => onControl?.({ topN: n })}>{n}</button>)}</span>
        <span>Lookback: {[30,45,90,180].map((d) => <button key={d} data-testid={`darkpool-lookback-${d}`} onClick={() => onControl?.({ lookback: d })}>{d}d</button>)}</span>
      </div>
      <table>
        <thead><tr><th>Time</th><th>Ticker</th><th>Price</th><th>Size</th><th>Notional</th><th>Sector</th><th>Level</th><th>Date</th></tr></thead>
        <tbody>
          {prints.map((p, i) => (
            <tr key={i} data-testid="darkpool-row">
              <td>{p.time ?? '—'}</td><td>{p.ticker}</td><td>{p.price ?? '—'}</td><td>{p.size ?? '—'}</td><td>{p.notional != null ? fmtUSD(p.notional) : '—'}</td><td>{p.sector ?? 'Unknown'}</td><td title="Off-exchange print. No side or direction is known. Level shows where size transacted.">{p.level != null ? `DP ${fmtUSD(p.level)} · ${p.date ?? ''}` : '—'}</td><td>{p.date ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {levels && levels.length > 0 && (
        <div data-testid="darkpool-levels" title="Off-exchange print. No side or direction is known. Level shows where size transacted.">
          {levels.map((l, i) => <span key={i} data-testid="darkpool-level">{`DP ${fmtUSD(l.notional)} · ${l.date}`}</span>)}
        </div>
      )}
    </div>
  );
}

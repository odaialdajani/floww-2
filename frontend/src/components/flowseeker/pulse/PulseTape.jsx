import React, { useMemo } from 'react';
import { spreadPosition } from './spreadPosition.js';
import { highlightFlags } from '../highlighting/highlighting.js';
import { fmtUSD, fmtK } from '../scanLogic.js';

// PulseTape columns: Fill, Side (BID/MID/ASK/NO_QUOTE), spread-position bar, highlighting, + honest states.
function SpreadBar({ last, bid, ask }) {
  const sp = spreadPosition(last, bid, ask);
  if (sp.side === 'NO_QUOTE' || sp.side === 'LOCKED') {
    const title = sp.side === 'LOCKED' ? 'Locked/crossed spread — no fill' : 'No quote — spread unavailable';
    const label = sp.side === 'LOCKED' ? 'LOCKED' : '—';
    return <span className="fsb-spread fsb-spread--noquote" data-testid="spread-noquote" title={title}>{label}</span>;
  }
  const pct = Math.round((sp.position ?? 0) * 100);
  return (
    <span className="fsb-spread" data-testid="spread-bar" title={`${sp.side} ${pct}%`}>
      <span className="fsb-spread__track"><span className="fsb-spread__fill" style={{ width: `${pct}%` }} /></span>
      <span className="fsb-spread__label">{sp.side}</span>
    </span>
  );
}

export default function PulseTape({ rows, state = 'ready', onRowClick, frozen = false }) {
  const list = Array.isArray(rows) ? rows : [];

  if (state === 'loading') return <div className="fsb-pulse fsb-pulse--loading" data-testid="pulse-loading">Loading tape…</div>;
  if (state === 'error') return <div className="fsb-pulse fsb-pulse--error" data-testid="pulse-error">Tape unavailable</div>;
  if (state === 'empty' || list.length === 0) {
    return <div className="fsb-pulse fsb-pulse--empty" data-testid="pulse-empty">No prints in window — waiting for flow</div>;
  }

  return (
    <div className={`fsb-pulse${frozen ? ' fsb-pulse--frozen' : ''}`} data-testid="pulse-tape">
      {frozen && <div className="fsb-pulse__frozen" data-testid="pulse-frozen">Paused</div>}
      <table className="fsb-pulse__table">
        <thead><tr><th>Time</th><th>Ticker</th><th>Strike</th><th>C/P</th><th>Fill</th><th>Side</th><th>Spread</th><th>Prem</th></tr></thead>
        <tbody>
          {list.map((r, i) => {
            const h = highlightFlags(r);
            const cls = h.sizeGtOI ? 'fsb-row--size-gt-oi' : h.volGtOI ? 'fsb-row--vol-gt-oi' : '';
            const key = `${r.ticker ?? r.under}-${r.strike}-${r.exp ?? r.expiration}-${i}`;
            const fill = r.premium != null ? fmtUSD(r.premium) : '—';
            const side = (() => {
              const sp = spreadPosition(r.last, r.bid, r.ask);
              return sp.side;
            })();
            return (
              <tr key={key} className={cls} data-testid="pulse-row" data-side={side} onClick={() => onRowClick?.(r)} role={onRowClick ? 'button' : undefined}>
                <td>{r.timestamp ? new Date(r.timestamp).toLocaleTimeString() : '—'}</td>
                <td>{r.ticker ?? r.under ?? '—'}</td>
                <td>{r.strike ?? '—'}</td>
                <td>{String(r.type ?? '').toUpperCase() || '—'}</td>
                <td data-testid="pulse-fill">{fill}</td>
                <td data-testid="pulse-side">{side}</td>
                <td><SpreadBar last={r.last} bid={r.bid} ask={r.ask} /></td>
                <td>{r.premium != null ? fmtUSD(r.premium) : '—'}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

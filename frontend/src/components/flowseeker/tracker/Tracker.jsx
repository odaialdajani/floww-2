import React, { useEffect, useState, useCallback } from 'react';
import { loadTracker, removeBookmark, trackerPL, trackerStatus } from './trackerStore.js';
import { fmtUSD } from '../scanLogic.js';

export default function Tracker({ quotes = {}, state = 'ready' }) {
  const [items, setItems] = useState(() => loadTracker());

  const refresh = useCallback(() => setItems(loadTracker()), []);
  useEffect(() => {
    const h = () => refresh();
    window.addEventListener('storage', h);
    return () => window.removeEventListener('storage', h);
  }, [refresh]);

  const onRemove = (id) => setItems(removeBookmark(id));

  if (state === 'loading') return <div data-testid="tracker-loading">Loading tracker…</div>;
  if (state === 'error') return <div data-testid="tracker-error">Tracker unavailable</div>;
  if (!items.length) return <div data-testid="tracker-empty">No tracked trades — bookmark a row to track P/L</div>;

  return (
    <div data-testid="tracker-list">
      <table className="fsb-tracker__table">
        <thead><tr><th>Ticker</th><th>Contract</th><th>Entry</th><th>Mark</th><th>P/L</th><th>Status</th><th /></tr></thead>
        <tbody>
          {items.map((e) => {
            const q = quotes[e.id] || null;
            const { pl, mark, state: plState } = trackerPL(e, q);
            const status = trackerStatus(e, q?.oiInfo ?? null);
            return (
              <tr key={e.id} data-testid="tracker-row">
                <td>{e.ticker}</td>
                <td>{e.strike} {String(e.type).toUpperCase()} {e.exp}</td>
                <td>{e.entryPrice != null ? fmtUSD(e.entryPrice * 100) : '—'}</td>
                <td data-testid="tracker-mark">{mark != null ? fmtUSD(mark * 100) : plState === 'stale' ? 'stale' : '—'}</td>
                <td data-testid="tracker-pl">{pl != null ? fmtUSD(pl) : '—'}</td>
                <td data-testid="tracker-status" title="Proxy based on OI drift/volume">{status}</td>
                <td><button onClick={() => onRemove(e.id)} data-testid="tracker-remove">×</button></td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="fsb-tracker__proxy-note">Close detection is a proxy based on OI drift/volume.</p>
    </div>
  );
}

import React from 'react';
import { fmtUSD } from '../scanLogic.js';

export function NetPremiumTrend({ series, state = 'ready' }) {
  if (state === 'loading') return <div data-testid="trend-loading">Loading trend…</div>;
  if (!series || series.length === 0) return <div data-testid="trend-empty">No premium history — building</div>;
  if (state === 'stale') return <div data-testid="trend-stale">Stale</div>;
  return (
    <div data-testid="trend-chart">
      <h4>Net Premium trend</h4>
      <ul>{series.map((p, i) => <li key={i} data-testid="trend-point">{p.date}: {fmtUSD(p.value)}</li>)}</ul>
    </div>
  );
}

export function StrikeDistribution({ buckets, state = 'ready' }) {
  if (state === 'loading') return <div data-testid="strike-loading">Loading distribution…</div>;
  if (!buckets || buckets.length === 0) return <div data-testid="strike-empty">No strike data</div>;
  return (
    <div data-testid="strike-dist">
      <h4>Strike Distribution</h4>
      <ul>{buckets.map((b, i) => <li key={i} data-testid="strike-bucket">{b.strike}: {fmtUSD(b.premium)}</li>)}</ul>
    </div>
  );
}

export function VolOiFooter({ rows14d, state = 'ready' }) {
  if (state === 'loading') return <div data-testid="voloi-loading">Loading Vol/OI…</div>;
  if (!rows14d || rows14d.length === 0) return <div data-testid="voloi-empty">No Vol/OI history — needs cadence</div>;
  return (
    <div data-testid="voloi-table">
      <h4>Vol/OI 14d</h4>
      <table><tbody>{rows14d.map((r, i) => <tr key={i} data-testid="voloi-row"><td>{r.date}</td><td>{r.vol}</td><td>{r.oi}</td></tr>)}</tbody></table>
    </div>
  );
}

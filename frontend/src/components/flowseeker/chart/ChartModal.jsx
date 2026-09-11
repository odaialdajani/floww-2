import React, { useState } from 'react';
import { fmtUSD } from '../scanLogic.js';

// Chart modal v1 — only Contract history + Net Premium. Five views is scope creep.
const STEPS = [
  'NetPrem 5-7D',
  'Underlying $',
  'Contract + IV + RVOL',
  'Strike 1W',
  'Vol/OI 14d',
  'Heatseeker cross-check',
];

export default function ChartModal({ row, open, onClose, history = [], netPremiumSeries = [] }) {
  const [checks, setChecks] = useState(() => ({}));
  const [verdict, setVerdict] = useState(null);

  if (!open || !row) return null;

  const toggle = (i) => setChecks((c) => ({ ...c, [i]: !c[i] }));

  return (
    <div className="fsb-modal" data-testid="chart-modal" role="dialog" aria-modal="true">
      <div className="fsb-modal__backdrop" onClick={onClose} data-testid="chart-backdrop" />
      <div className="fsb-modal__panel">
        <div className="fsb-modal__header">
          <span>{row.ticker ?? row.under} {row.strike} {String(row.type).toUpperCase()} {row.exp ?? row.expiration}</span>
          <button onClick={onClose} data-testid="chart-close">×</button>
        </div>
        <div className="fsb-modal__body">
          <section data-testid="chart-history">
            <h4>Contract history</h4>
            {history.length === 0 ? (
              <div data-testid="chart-history-empty" title="No scans yet — run a scan to populate history">No history yet — run a scan</div>
            ) : (
              <ul>{history.map((h, i) => <li key={i} data-testid="chart-history-row">{h.date}: {fmtUSD(h.premium ?? 0)}</li>)}</ul>
            )}
          </section>
          <section data-testid="chart-netprem">
            <h4>Net Premium</h4>
            {netPremiumSeries.length === 0 ? (
              <div data-testid="chart-netprem-empty" title="No premium series until at least one scan completes">No premium series yet — run a scan</div>
            ) : (
              <ul>{netPremiumSeries.map((p, i) => <li key={i}>{p.label}: {fmtUSD(p.value)}</li>)}</ul>
            )}
          </section>
          <section data-testid="chart-checklist">
            <h4>Investigation checklist</h4>
            {STEPS.map((label, i) => (
              <label key={i} data-testid="checklist-item">
                <input type="checkbox" checked={!!checks[i]} onChange={() => toggle(i)} data-testid={`check-${i}`} /> {label}
              </label>
            ))}
            <div className="fsb-modal__verdict">
              <button onClick={() => setVerdict('confirmed')} data-testid="verdict-confirmed">Confirmed</button>
              <button onClick={() => setVerdict('skipped')} data-testid="verdict-skipped">Skipped</button>
              {verdict && <span data-testid="verdict-label">{verdict}</span>}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

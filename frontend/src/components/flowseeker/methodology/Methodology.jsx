import React from 'react';

export function Checklist({ steps, checks, onToggle, verdict, onVerdict }) {
  return (
    <div data-testid="checklist">
      {steps.map((label, i) => (
        <label key={i} data-testid="checklist-item">
          <input type="checkbox" checked={!!checks[i]} onChange={() => onToggle(i)} data-testid={`check-${i}`} /> {label}
        </label>
      ))}
      <div>
        <button onClick={() => onVerdict('confirmed')} data-testid="verdict-confirmed">Confirmed</button>
        <button onClick={() => onVerdict('skipped')} data-testid="verdict-skipped">Skipped</button>
        {verdict && <span data-testid="verdict-label">{verdict}</span>}
      </div>
    </div>
  );
}

export function FunnelEmpty({ beforeCount, afterCount, actions, onWiden }) {
  if (afterCount > 0) return null;
  return (
    <div data-testid="funnel-empty">
      <span>0 rows — widen shortage ({beforeCount} → {afterCount})</span>
      {actions.map((a) => <button key={a.action} data-testid={`funnel-${a.action}`} onClick={() => onWiden(a.action)}>{a.label}</button>)}
    </div>
  );
}

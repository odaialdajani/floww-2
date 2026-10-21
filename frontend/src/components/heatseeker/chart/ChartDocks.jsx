import React, { useState } from 'react';
// B14 focused-pane sidecars: reuse maps without duplicating dashboards.
// Stale scopes badged, tombstones keep deletions removed, subscriptions capped.
// The dock is a FRAME, not a dashboard: map entries come from the consumer's
// existing map state (never a parallel fetch), and the sidecar content is the
// EXISTING Market/map component injected by the consumer — the dock never
// re-implements one. Explicit focused-symbol policy: unavailable (no focus),
// missing (no map entry), removed (tombstone — deleted symbols stay removed),
// stale (badged), ok (sidecar renders).
export const MAX_SUBSCRIPTIONS = 10;
export function capSubscriptions(symbols) {
  return (Array.isArray(symbols) ? symbols : []).slice(0, MAX_SUBSCRIPTIONS);
}
export function sidecarFor(focusedSymbol, maps) {
  if (!focusedSymbol || !maps) return { status: 'unavailable' };
  const entry = maps[focusedSymbol];
  if (!entry) return { status: 'missing' };
  if (entry.tombstone) return { status: 'removed' };
  if (entry.stale) return { status: 'stale', data: entry.data };
  return { status: 'ok', data: entry.data };
}

const BADGE_TEXT = {
  unavailable: 'dock unavailable — no focused symbol',
  missing: 'no map entry for the focused symbol',
  removed: 'removed from the map — stays removed',
  stale: 'stale map — readings not current',
};

export default function ChartDocks({ focusedSymbol, maps = {}, subscriptionSymbols = [], renderSidecar = null, title = 'Map & Market docks' }) {
  const sidecar = sidecarFor(focusedSymbol, maps);
  // Fetch subscriptions are capped: the dock watches at most
  // MAX_SUBSCRIPTIONS symbols and shows the census honestly.
  const capped = capSubscriptions(subscriptionSymbols);
  // Only live entries dock sidecar content. Tombstones keep deleted symbols
  // removed; missing/unavailable never invent an entry.
  const dockable = sidecar.status === 'ok' || sidecar.status === 'stale';
  const [open, setOpen] = useState(false);
  return (
    <section className="chart-docks" data-testid="chart-docks" data-status={sidecar.status}
      data-symbol={focusedSymbol || ''} aria-label="Chart docks">
      <header className="chart-docks-head">
        <strong>{title}</strong>
        {sidecar.status !== 'ok' && (
          <span className="chart-docks-badge" data-testid="dock-badge" data-status={sidecar.status}>
            {BADGE_TEXT[sidecar.status]}
          </span>
        )}
      </header>
      <p className="chart-docks-focus" data-testid="dock-focus">focused {focusedSymbol || 'none'}</p>
      <p className="chart-docks-subs" data-testid="dock-subs">{capped.length} of {MAX_SUBSCRIPTIONS} subscriptions</p>
      {dockable && renderSidecar && (
        <details className="chart-docks-sidecar" data-testid="dock-sidecar" open={open}>
          {/* Controlled toggle: the summary owns the state (jsdom does not
              implement the browser's summary activation behavior, and real
              browsers keep working through the same handler). */}
          <summary role="button" onClick={(event) => { event.preventDefault(); setOpen(v => !v); }}>Open {focusedSymbol} sidecar</summary>
          {/* The consumer injects the EXISTING map/Market component here —
              lazily, only once opened, so the dock adds no always-on load. */}
          {open ? renderSidecar(sidecar, focusedSymbol) : null}
        </details>
      )}
    </section>
  );
}

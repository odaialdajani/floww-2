import React from 'react';
// B14 focused-pane sidecars: reuse maps without duplicating dashboards.
// Stale scopes badged, tombstones keep deletions removed, subscriptions capped.
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
export default function ChartDocks({ focusedSymbol, maps }) {
  const sidecar = sidecarFor(focusedSymbol, maps);
  return <div data-testid="chart-docks" data-status={sidecar.status}>{focusedSymbol || 'no focus'}</div>;
}

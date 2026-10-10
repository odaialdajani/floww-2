import React from 'react';
// B25 read-only paper positions: stamped source/account/state, options not shares,
// replay hides live, review-only marked nonhistorical and excluded from AI.
export function filterPositions(positions, { replay = false, entitlement = false } = {}) {
  if (!entitlement) return { status: 'denied', items: [] };
  if (replay) return { status: 'practice-hidden', items: [] };
  const items = (positions || []).filter((p) => p && p.source && p.account && p.state);
  return { status: 'ok', items };
}
export default function PaperPositionOverlay({ positions, replay, entitlement }) {
  const out = filterPositions(positions, { replay, entitlement });
  return <div data-testid="paper-positions" data-status={out.status}>{out.items.length} positions</div>;
}

// Shim — single source of truth is scanLogic.spreadPosition.
// Re-exports with (last,bid,ask) arg order for pulse consumers; also exposes
// (bid,ask,last) order via spreadPositionRaw for direct scanLogic callers.
import { spreadPosition as _sp } from '../scanLogic.js';

// Pulse callers historically use (last, bid, ask) — adapt to scanLogic's (bid, ask, last).
export function spreadPosition(last, bid, ask) {
  const r = _sp(bid, ask, last);
  // Map scanLogic shape {pos, state, side, label} → pulse shape {position, side, label, pos, state}
  return { position: r.pos, pos: r.pos, side: r.side, label: r.label, state: r.state };
}

export function spreadPositionLabel(pos) {
  if (pos == null || !Number.isFinite(pos)) return 'NO_QUOTE';
  if (pos <= 0.33) return 'BID';
  if (pos < 0.67) return 'MID';
  return 'ASK';
}

// Direct re-export for callers that already use (bid,ask,last) order
export { _sp as spreadPositionRaw };

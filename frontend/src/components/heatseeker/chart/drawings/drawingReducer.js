// B16 logical drawings: anchors survive zoom, drag suppresses pan, OHLC magnet,
// cancel/undo/delete/lock/hide. Tools: horizontal/trend/vertical/rectangle/text/arrow.
export const TOOLS = ['horizontal', 'trend', 'vertical', 'rectangle', 'text', 'arrow'];
export function createDrawing(tool, anchors) {
  if (!TOOLS.includes(tool)) throw new Error('unsupported-tool');
  return { id: Math.random().toString(36).slice(2), tool, anchors, visible: true, locked: false, revision: 1 };
}
export function magnet(price, ohlc) {
  const cands = [ohlc.open, ohlc.high, ohlc.low, ohlc.close].filter((v) => Number.isFinite(v));
  let best = price, bd = Infinity;
  for (const c of cands) { const d = Math.abs(c - price); if (d < bd) { bd = d; best = c; } }
  return best;
}
export function reduceDrawings(state, action) {
  switch (action.type) {
    case 'add': return [...state, action.drawing];
    case 'delete': return state.filter((d) => d.id !== action.id);
    case 'lock': return state.map((d) => (d.id === action.id ? { ...d, locked: true } : d));
    case 'hide': return state.map((d) => (d.id === action.id ? { ...d, visible: false } : d));
    case 'undo': return state.slice(0, -1);
    default: return state;
  }
}

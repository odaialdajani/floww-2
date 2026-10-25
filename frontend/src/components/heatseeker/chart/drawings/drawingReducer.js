// B16 logical drawings: anchors survive zoom, drag suppresses pan, OHLC magnet,
// cancel/undo/delete/lock/hide. Tools: horizontal/trend/vertical/rectangle/text/arrow.
// B17: the nine evidence-backed registry tools — brush, fib and horizontal-ray
// create and render through the SAME reducer/geometry as the basics.
// Anchors are LOGICAL {t,p} values (epoch ms, price) — never pixels. Projection
// maps them through the current viewport, so zoom/resize changes where they
// render but never what they mean.
import { fibPrices, riskLevels } from './advancedTools';
export const TOOLS = ['horizontal', 'trend', 'vertical', 'rectangle', 'text', 'arrow', 'horizontal-ray', 'brush', 'fib', 'risk'];
export function createDrawing(tool, anchors, extra = {}) {
  if (!TOOLS.includes(tool)) throw new Error('unsupported-tool');
  // Only known-safe extras merge (side for the risk tool); anything else —
  // especially secrets or broker fields — never touches a drawing.
  const { side, style } = extra || {};
  return { id: Math.random().toString(36).slice(2), tool, anchors, visible: true, locked: false, revision: 1,
    ...(side ? { side } : {}), ...(style ? { style } : {}) };
}
export function magnet(price, ohlc) {
  const cands = [ohlc.open, ohlc.high, ohlc.low, ohlc.close].filter((v) => Number.isFinite(v));
  let best = price, bd = Infinity;
  for (const c of cands) { const d = Math.abs(c - price); if (d < bd) { bd = d; best = c; } }
  return best;
}

// Viewport from the REAL loaded frames: time domain from frame times, price
// domain from observed lows/highs (padded so lines never touch the edge).
// Unknown/empty frames produce an honest zero viewport callers must refuse.
export function viewportFor(frames, width = 600, height = 320) {
  const list = (Array.isArray(frames) ? frames : []).filter(f => f && Number.isFinite(Date.parse(f.time)) && Number.isFinite(f.low) && Number.isFinite(f.high));
  if (!list.length || !(width > 0) || !(height > 0)) return null;
  const times = list.map(f => Date.parse(f.time));
  const lows = list.map(f => f.low);
  const highs = list.map(f => f.high);
  const tMin = Math.min(...times), tMax = Math.max(...times);
  const rawPMin = Math.min(...lows), rawPMax = Math.max(...highs);
  const pad = (rawPMax - rawPMin) * 0.05 || 1;
  return { width, height, tMin, tMax: tMax === tMin ? tMin + 1 : tMax, pMin: rawPMin - pad, pMax: rawPMax + pad };
}

// Logical -> pixel. The anchor itself is never mutated by zoom/resize.
export function projectAnchor(anchor, vp) {
  if (!anchor || !vp) return null;
  const { t, p } = anchor;
  if (!Number.isFinite(t) || !Number.isFinite(p)) return null;
  const x = vp.xForTime ? vp.xForTime(t) : ((t - vp.tMin) / (vp.tMax - vp.tMin)) * vp.width;
  const y = vp.height - ((p - vp.pMin) / (vp.pMax - vp.pMin)) * vp.height;
  return { x, y };
}

// Pixel -> logical (pointer geometry starts here).
export function unprojectPoint({ x, y }, vp) {
  if (!vp || !Number.isFinite(x) || !Number.isFinite(y)) return null;
  const t = vp.timeForX ? vp.timeForX(x) : vp.tMin + (x / vp.width) * (vp.tMax - vp.tMin);
  const p = vp.pMin + ((vp.height - y) / vp.height) * (vp.pMax - vp.pMin);
  return { t, p };
}

// OHLC-ONLY magnet for pointer geometry: snap a {t,p} point to the nearest
// frame's open/high/low/close. Candidates come ONLY from that frame's OHLC —
// never from mid/fib/derived prices. Radius is relative to the price range;
// outside it the raw price is kept (honest, no invented snap).
export function magnetPoint(point, frames, radius = 0.25, vp = viewportFor(frames)) {
  if (!point || !vp) return point;
  const list = (Array.isArray(frames) ? frames : []).filter(f => f && Number.isFinite(Date.parse(f.time)));
  if (!list.length) return point;
  const t = Number.isFinite(point.t) ? point.t : Date.parse(point.t);
  let nearest = null, bestDt = Infinity;
  for (const frame of list) {
    const dt = Math.abs(Date.parse(frame.time) - t);
    if (dt < bestDt) { bestDt = dt; nearest = frame; }
  }
  if (!nearest) return point;
  const snappedTime = Date.parse(nearest.time);
  const raw = magnet(point.p, nearest);
  const range = vp.pMax - vp.pMin;
  const within = Math.abs(raw - point.p) <= radius * range;
  return { t: snappedTime, p: within ? raw : point.p };
}

// Keyboard geometry: arrows nudge every anchor by a logical step.
export function nudgeDrawing(drawing, dt, dp) {
  return { ...drawing, anchors: drawing.anchors.map(a => ({ t: a.t + dt, p: a.p + dp })), revision: (drawing.revision || 1) + 1 };
}
export function canEdit(drawing) { return !!drawing && drawing.locked !== true; }

// Interaction arbitration: a selected-drawing drag suppresses chart pan. The
// engine consults this before starting a pan.
export function suppressesPan(interaction) {
  return interaction?.mode === 'drawing-drag' && !!interaction.id;
}

// Geometry descriptor per tool (rendering contract for the drawing layer).
// `extra` carries the drawing itself (risk side, style) where the tool needs it.
export function geometryFor(tool, anchors, vp, extra = null) {
  if (!Array.isArray(anchors) || !anchors.length) return null;
  const points = anchors.map(a => projectAnchor(a, vp)).filter(Boolean);
  if (!points.length) return null;
  if (tool === 'horizontal') return {kind:'line',points:[{x:0,y:points[0].y},{x:vp.width,y:points[0].y}]};
  if (tool === 'horizontal-ray') return {kind:'line',points:[{x:points[0].x,y:points[0].y},{x:vp.width,y:points[0].y}]};
  if (tool === 'fib') {
    // B17: the seven evidence-backed levels across the anchors' span. High/low
    // come from the two anchor prices — the SAME math as advancedTools.fibPrices.
    const [a, b] = anchors;
    if (!b) return null;
    const high = Math.max(Number(a.p), Number(b.p));
    const low = Math.min(Number(a.p), Number(b.p));
    const levels = fibPrices(high, low).map(level => ({
      ratio: level.ratio,
      price: level.price,
      points: [{ x: points[0].x, y: points[0].y === null ? 0 : projectAnchor({ t: a.t, p: level.price }, vp).y }, { x: points[1].x, y: projectAnchor({ t: b.t, p: level.price }, vp).y }],
    }));
    return { kind: 'fib', levels };
  }
  if (tool === 'vertical') return {kind:'line',points:[{x:points[0].x,y:0},{x:points[0].x,y:vp.height}]};
  if (tool === 'rectangle') {
    const [a, b] = points;
    if (!b) return null;
    return { kind: 'rect', x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), width: Math.abs(b.x - a.x), height: Math.abs(b.y - a.y) };
  }
  if (tool === 'text') return { kind: 'label', x: points[0].x, y: points[0].y };
  if (tool === 'risk') {
    // CHART-C090: three order-independent anchors -> sorted entry/stop/target
    // levels for the drawing's side; degenerate inputs render NOTHING (the
    // helper refuses), so no zone or R-multiple is ever fabricated.
    const levels = riskLevels(anchors.map(a => a.p), extra?.side || 'long');
    if (!levels) return null;
    const xs = points.map(p => p.x);
    const x0 = Math.min(...xs), x1 = Math.max(...xs);
    if (!(x1 > x0)) return null;
    const yFor = price => projectAnchor({ t: anchors[0].t, p: price }, vp).y;
    return { kind: 'risk', side: levels.side, rMultiple: levels.rMultiple, x0, x1,
      levels: [['entry', levels.entry], ['stop', levels.stop], ['target', levels.target]]
        .map(([role, price]) => ({ role, price, y: yFor(price) })) };
  }
  return { kind: 'line', points };
}

export function reduceDrawings(state, action) {
  switch (action.type) {
    case 'add': return [...state, action.drawing];
    case 'delete': return state.filter((d) => d.id !== action.id);
    case 'lock': return state.map((d) => (d.id === action.id ? { ...d, locked: true } : d));
    case 'hide': return state.map((d) => (d.id === action.id ? { ...d, visible: false } : d));
    case 'undo': return state.slice(0, -1);
    case 'toggleLock': return state.map((d) => (d.id === action.id ? { ...d, locked: !d.locked } : d));
    case 'toggleVisible': return state.map((d) => (d.id === action.id ? { ...d, visible: d.visible === false } : d));
    // Edit/replace anchors: locked drawings refuse — returned unchanged.
    case 'update': return state.map((d) => (d.id === action.id && canEdit(d) ? { ...d, anchors: action.anchors, revision: (d.revision || 1) + 1 } : d));
    // B17 style model: per-drawing optional {color?, width?, dash?} merged
    // additively; absent keys keep incumbent defaults; locked refuses.
    case 'style': return state.map((d) => (d.id === action.id && canEdit(d) ? { ...d, style: { ...(d.style || {}), ...action.style }, revision: (d.revision || 1) + 1 } : d));
    case 'nudge': return state.map((d) => (d.id === action.id && canEdit(d) ? nudgeDrawing(d, action.dt || 0, action.dp || 0) : d));
    default: return state;
  }
}

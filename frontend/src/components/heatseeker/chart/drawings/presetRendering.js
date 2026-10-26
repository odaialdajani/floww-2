// B17 / CHART-C130 — the PRESET RENDERING ADAPTER (pure).
// Contract: autonomous-20261025/preset-rendering-adapter-interface.md.
//
// buildPresetRenderSpec({ tool, anchors, viewport, style, selected })
//   -> { status: 'ok'|'refused', reason?, primitives, hitGeometry, notes }
//
// A pure adapter over the EXISTING drawing geometry/projection
// (drawingReducer.geometryFor / projectAnchor) — NOT a second drawing
// engine. Every level/line/rect position comes from the same transform the
// incumbent renderer uses; this module only decides WHICH primitives exist
// and what style each carries. Absent style fields keep the incumbent
// rendering defaults byte-for-byte (default equivalence is pinned).
//
// Scope discipline (the interface's rule): a field with no approved visible
// semantic is recorded in `notes` as an explicit hold/noop — never silently
// consumed. Fib 'color' is the TRENDLINE color only; per-level colors come
// from levelColors and are never overridden by it. Risk keeps its semantic
// role colors (entry/stop/target) no matter what generic style is passed —
// the risk box stays an analysis drawing, never a broker intent.
//
// Pure: no React, no fetch, no storage, no session/account surface. Inputs
// are never mutated; the output is JSON-serializable and carries no
// credentials, preset state, or account data.

import { geometryFor, projectAnchor } from './drawingReducer';
import { isSupportedTool, toolFamily } from './toolRegistry';
import { fibPrices } from './advancedTools';

// Incumbent rendering defaults (PriceNodeHistory's renderDrawingLayer today):
// a style-absent drawing renders EXACTLY like this.
const INCUMBENT = {
  stroke: (selected) => (selected ? '#e3c16a' : '#7fa6c0'),
  strokeWidth: (selected) => (selected ? 2 : 1.2),
  dash: undefined,
  fibLabelFill: (selected) => (selected ? '#e3c16a' : '#8fa6ba'),
  labelFill: '#dce8f2',
  riskRoles: { entry: '#e3c16a', stop: '#d65656', target: '#5ec986' },
  riskZones: { stop: 'rgba(214,86,86,0.14)', target: 'rgba(94,201,134,0.10)' },
  metaFill: '#8fa6ba',
};

function hexToRgb(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(String(hex || ''));
  if (!m) return null;
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
function withAlpha(hex, alpha) {
  const rgb = hexToRgb(hex);
  return rgb ? `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${alpha})` : null;
}

const lineSpec = (points, stroke, strokeWidth, dash, meta) => ({
  kind: 'polyline', points: points.map((p) => ({ x: p.x, y: p.y })),
  stroke, strokeWidth, ...(dash ? { dash: '6 3' } : {}), ...(meta ? { meta } : {}),
});

// Extend a two-point segment to the domain edges along its EXISTING slope.
function extendToDomain(points, vp, extendLeft, extendRight) {
  const [a, b] = points;
  if (!a || !b) return points.map((p) => ({ ...p }));
  if (a.x === b.x) return points.map((p) => ({ ...p })); // vertical: already full height
  const slope = (b.y - a.y) / (b.x - a.x);
  const at = (x) => ({ x, y: a.y + slope * (x - a.x) });
  const out = [];
  out.push(extendLeft ? at(0) : { ...a });
  out.push(extendRight ? at(vp.width) : { ...b });
  return out;
}

// Fib level prices through the SAME math as advancedTools.fibPrices, with
// the preset's ratios and direction/scale semantics:
//   forward:  price = high - (high - low) * ratio   (fibPrices convention)
//   reverse:  price = low  + (high - low) * ratio   (retracement mirrored)
//   logScale: interpolation in log space (geometric levels); nonpositive
//             anchors REFUSE — never NaN geometry.
function fibLevelPrices(high, low, ratios, { reverse, logScale }) {
  if (logScale) {
    if (!(high > 0) || !(low > 0)) return null; // caller turns this into a refusal
    const lnH = Math.log(high), lnL = Math.log(low);
    return ratios.map((r) => Math.exp(reverse ? lnL + (lnH - lnL) * r : lnH - (lnH - lnL) * r));
  }
  return ratios.map((r) => (reverse ? low + (high - low) * r : high - (high - low) * r));
}

export function buildPresetRenderSpec({ tool, anchors, viewport, style, selected } = {}) {
  const notes = [];
  if (!isSupportedTool(tool)) {
    return { status: 'refused', reason: 'unsupported tool: ' + tool, primitives: [], hitGeometry: null, notes };
  }
  const st = style || {};
  const family = toolFamily(tool);
  // The geometry source of truth — the SAME call the incumbent renderer makes.
  const g = geometryFor(tool, anchors, viewport, { side: st.side });
  if (!g) {
    return { status: 'refused', reason: 'no geometry for the given anchors/viewport', primitives: [], hitGeometry: null, notes };
  }
  const stroke = st.color || INCUMBENT.stroke(selected);
  const strokeWidth = st.width || INCUMBENT.strokeWidth(selected);
  const dash = st.dash ? '6 3' : undefined;
  const primitives = [];

  if (family === 'line') {
    if (tool === 'text') {
      // label family handled below; unreachable guard
    }
    const isSpan = tool === 'horizontal' || tool === 'vertical';
    const pts = (g.kind === 'line' ? g.points : (g.points || []));
    let points = pts;
    if (!isSpan && st.extendLeft === undefined && st.extendRight === undefined) {
      points = pts; // incumbent: no extension
    } else if (!isSpan) {
      points = extendToDomain(pts, viewport, !!st.extendLeft, !!st.extendRight);
    } else if (st.extendLeft || st.extendRight) {
      notes.push({ field: 'extendLeft', scope: 'noop', reason: tool + ' already spans the domain' });
    }
    primitives.push(lineSpec(points, stroke, strokeWidth, dash, { part: 'line' }));
    if (st.showLabels === true) {
      const last = points[points.length - 1];
      primitives.push({
        kind: 'text', x: last.x + 4, y: last.y,
        text: String(anchors[anchors.length - 1].p),
        fontSize: 9, fill: INCUMBENT.fibLabelFill(selected), meta: { part: 'line-label' },
      });
    }
  } else if (family === 'shape') {
    if (tool === 'rectangle') {
      primitives.push({
        kind: 'rect', x: g.x, y: g.y, width: g.width, height: g.height,
        stroke, strokeWidth, ...(dash ? { dash } : {}),
        fill: st.fillOpacity > 0 ? (withAlpha(st.color || stroke, st.fillOpacity) || 'none') : 'none',
        meta: { part: 'rect' },
      });
    } else {
      // arrow keeps the incumbent marker contract; the caller owns the marker def
      primitives.push({ ...lineSpec(g.points, stroke, strokeWidth, dash, { part: 'line' }), marker: 'arrow' });
      if (st.fillOpacity !== undefined) {
        notes.push({ field: 'fillOpacity', scope: 'hold', reason: 'arrow has no fill region' });
      }
    }
  } else if (family === 'free') {
    primitives.push(lineSpec(g.points, stroke, strokeWidth, dash, { part: 'brush' }));
  } else if (family === 'label') {
    primitives.push({
      kind: 'text', x: g.x, y: g.y, text: (anchors[0] && anchors[0].text) || 'text',
      fontSize: st.fontSize || 12, fill: st.color || INCUMBENT.labelFill,
      stroke, strokeWidth, ...(dash ? { dash } : {}), meta: { part: 'label' },
    });
  } else if (family === 'fib') {
    const [a, b] = anchors;
    const high = Math.max(a.p, b.p);
    const low = Math.min(a.p, b.p);
    const hasFibStyle = ['ratios', 'levelColors', 'showLevels', 'fillOpacity', 'extensions', 'trendline', 'labels', 'logScale', 'reverse'].some((k) => st[k] !== undefined);
    if (!hasFibStyle) {
      // DEFAULT EQUIVALENCE: the incumbent fib — all levels, common color,
      // always-labeled, no trendline, no fills.
      for (const level of g.levels) {
        primitives.push(lineSpec(level.points, stroke, strokeWidth, dash, { part: 'level', ratio: level.ratio }));
        primitives.push({
          kind: 'text', x: level.points[1].x + 4, y: level.points[1].y,
          text: String(level.ratio), fontSize: 9,
          fill: INCUMBENT.fibLabelFill(selected), meta: { part: 'level-label', ratio: level.ratio },
        });
      }
    } else {
      const ratios = Array.isArray(st.ratios) && st.ratios.length
        ? st.ratios.filter((r) => Number.isFinite(r))
        : (g.levels || []).map((l) => l.ratio);
      if (!ratios.length) {
        return { status: 'refused', reason: 'no finite fib ratios', primitives: [], hitGeometry: g, notes };
      }
      if (st.logScale && (!(high > 0) || !(low > 0))) {
        // REFUSED honestly — never NaN geometry; the drawing stays hit-testable.
        return { status: 'refused', reason: 'log scale requires positive anchor prices', primitives: [], hitGeometry: g, notes };
      }
      const prices = fibLevelPrices(high, low, ratios, { reverse: !!st.reverse, logScale: !!st.logScale });
      const ax = projectAnchor(a, viewport);
      const bx = projectAnchor(b, viewport);
      if (!ax || !bx) {
        return { status: 'refused', reason: 'no geometry for the given anchors/viewport', primitives: [], hitGeometry: g, notes };
      }
      const visible = ratios.map((_, i) => !(Array.isArray(st.showLevels) && st.showLevels[i] === false));
      const levelColor = (i) => (Array.isArray(st.levelColors) && typeof st.levelColors[i] === 'string'
        ? st.levelColors[i] : stroke);
      let prev = null; // for fills between consecutive VISIBLE levels
      for (let i = 0; i < ratios.length; i++) {
        const y = projectAnchor({ t: a.t, p: prices[i] }, viewport);
        const xEnd = st.extensions ? viewport.width : bx.x;
        if (visible[i]) {
          if (prev !== null && st.fillOpacity > 0) {
            const fill = withAlpha(levelColor(prev), st.fillOpacity);
            if (fill) {
              primitives.push({
                kind: 'band', x: ax.x, width: Math.max(1, xEnd - ax.x),
                y: Math.min(projectAnchor({ t: a.t, p: prices[prev] }, viewport).y, y.y),
                height: Math.abs(projectAnchor({ t: a.t, p: prices[prev] }, viewport).y - y.y),
                fill, meta: { part: 'band', between: [ratios[prev], ratios[i]] },
              });
            }
          }
          primitives.push(lineSpec(
            [{ x: ax.x, y: y.y }, { x: xEnd, y: y.y }],
            levelColor(i), st.width || strokeWidth, st.dash ? '6 3' : undefined,
            { part: 'level', ratio: ratios[i] },
          ));
          if (st.labels !== false) {
            primitives.push({
              kind: 'text', x: xEnd + 4, y: y.y, text: String(ratios[i]), fontSize: 9,
              fill: INCUMBENT.fibLabelFill(selected), meta: { part: 'level-label', ratio: ratios[i] },
            });
          }
          prev = i;
        }
      }
      // The trendline is drawn ONLY when asked; fib 'color' is its color.
      if (st.trendline === true) {
        primitives.push(lineSpec([ax, bx], stroke, st.width || strokeWidth, st.dash ? '6 3' : undefined, { part: 'trendline' }));
      }
    }
  } else if (family === 'risk') {
    const roles = {};
    for (const l of g.levels) roles[l.role] = l;
    const zoneColor = { stop: INCUMBENT.riskRoles.stop, target: INCUMBENT.riskRoles.target };
    const zoneAlpha = (role) => {
      if (st.fillOpacity === undefined) return INCUMBENT.riskZones[role];
      if (!(st.fillOpacity > 0)) return null;
      const rgb = hexToRgb(zoneColor[role]);
      return rgb ? `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${st.fillOpacity})` : null;
    };
    const zones = [['stop', roles.entry, roles.stop], ['target', roles.entry, roles.target]];
    for (const [role, u, v] of zones) {
      if (!u || !v || !Number.isFinite(u.y) || !Number.isFinite(v.y)) continue;
      const fill = zoneAlpha(role);
      if (!fill) continue; // fillOpacity 0 -> no zone (zero survives)
      primitives.push({
        kind: 'rect', x: g.x0, width: Math.max(1, g.x1 - g.x0),
        y: Math.min(u.y, v.y), height: Math.abs(u.y - v.y),
        fill, stroke: 'none', meta: { part: 'zone', role },
      });
    }
    for (const l of g.levels) {
      primitives.push(lineSpec(
        [{ x: g.x0, y: l.y }, { x: g.x1, y: l.y }],
        INCUMBENT.riskRoles[l.role], // semantic role colors — generic style NEVER overrides
        st.width || strokeWidth, st.dash ? '6 3' : undefined,
        { part: 'role-line', role: l.role },
      ));
      primitives.push({
        kind: 'text', x: g.x1 + 4, y: l.y, text: l.role + ' ' + l.price, fontSize: 9,
        fill: INCUMBENT.metaFill, meta: { part: 'role-label', role: l.role },
      });
    }
    primitives.push({
      kind: 'text', x: g.x0, y: Math.min(...g.levels.map((l) => l.y)) - 4,
      text: 'R ' + g.rMultiple.toFixed(1) + ' · ' + g.side + ' · analysis only',
      fontSize: 10, fill: selected ? '#e3c16a' : '#8fa6ba', meta: { part: 'risk-title' },
    });
    if (st.side !== undefined && st.side !== g.side) {
      notes.push({ field: 'side', scope: 'hold', reason: 'the drawing carries its own side (geometry truth); the style side differs and is not applied' });
    }
  }
  return { status: 'ok', primitives, hitGeometry: g, notes };
}

// Explicit supported/refused field scope per family (for the consumer
// handoff; mirrors presetSchema.PRESET_STYLE_FIELDS).
export const RENDER_FIELD_SCOPE = {
  line: { supported: ['color', 'width', 'dash', 'extendLeft', 'extendRight', 'showLabels'], noop: { horizontal: ['extendLeft', 'extendRight', 'span-already-full'], 'horizontal-ray': ['extendLeft'], vertical: ['extendLeft', 'extendRight'] } },
  shape: { supported: ['color', 'width', 'dash', 'fillOpacity'], hold: { arrow: ['fillOpacity'] } },
  free: { supported: ['color', 'width'] },
  fib: { supported: ['color', 'width', 'dash', 'ratios', 'levelColors', 'showLevels', 'fillOpacity', 'extensions', 'trendline', 'labels', 'logScale', 'reverse'], refused: { logScale: 'nonpositive anchor prices' } },
  label: { supported: ['color', 'fontSize'] },
  risk: { supported: ['color', 'width', 'dash', 'fillOpacity'], hold: { side: 'geometry truth; recorded as a note when it differs' } },
};

// B17/CHART-C130 focused pins — the PRESET RENDERING ADAPTER (pure module).
// RED-first: presetRendering.js does not exist yet. Contract:
// autonomous-20261025/preset-rendering-adapter-interface.md —
// buildPresetRenderSpec({tool, anchors, viewport, style, selected})
//   -> { status, reason?, primitives, hitGeometry, notes? }
// Pure over the EXISTING transform (drawingReducer geometryFor/projectAnchor);
// no React, no fetch, no storage, no second coordinate system.
import { buildPresetRenderSpec } from '../drawings/presetRendering';
import { geometryFor, projectAnchor } from '../drawings/drawingReducer';
import { defaultStyleForTool } from '../drawings/presetSchema';

const vp = { width: 600, height: 320, tMin: 0, tMax: 600, pMin: 90, pMax: 110 };
const A = (t, p) => ({ t, p });
const anchors = [A(100, 100), A(300, 95)];
const ok = (r) => expect(r.status).toBe('ok');

test('default equivalence: a style-absent trend drawing renders EXACTLY the incumbent spec', () => {
  const unselected = buildPresetRenderSpec({ tool: 'trend', anchors, viewport: vp });
  ok(unselected);
  expect(unselected.primitives).toHaveLength(1);
  const [line] = unselected.primitives;
  expect(line.kind).toBe('polyline');
  expect(line.points).toEqual(geometryFor('trend', anchors, vp).points); // the existing geometry, unchanged
  expect(line.stroke).toBe('#7fa6c0');   // incumbent unselected default
  expect(line.strokeWidth).toBe(1.2);
  expect(line.dash).toBeUndefined();
  expect(line.label).toBeUndefined();     // today's renderer draws no line labels
  const selected = buildPresetRenderSpec({ tool: 'trend', anchors, viewport: vp, selected: true });
  expect(selected.primitives[0].stroke).toBe('#e3c16a'); // incumbent selected tint
  expect(selected.primitives[0].strokeWidth).toBe(2);
});

test('line family: explicit color/width/dash consume; showLabels adds the price label only when true', () => {
  const styled = buildPresetRenderSpec({ tool: 'trend', anchors, viewport: vp,
    style: { color: '#e3c16a', width: 3, dash: true, showLabels: true } });
  ok(styled);
  const [line, label] = styled.primitives;
  expect(line.stroke).toBe('#e3c16a');
  expect(line.strokeWidth).toBe(3);
  expect(line.dash).toBe('6 3');
  expect(label.kind).toBe('text');
  expect(label.text).toBe(String(anchors[anchors.length - 1].p)); // the price at the labeled (end) point
  // absent showLabels -> no label primitive (default equivalence)
  const noLabels = buildPresetRenderSpec({ tool: 'trend', anchors, viewport: vp, style: { color: '#e3c16a' } });
  expect(noLabels.primitives.filter((p) => p.kind === 'text')).toHaveLength(0);
});

test('line extensions: extendLeft/extendRight reach the domain edges along the EXISTING slope, clipped', () => {
  const r = buildPresetRenderSpec({ tool: 'trend', anchors, viewport: vp,
    style: { extendLeft: true, extendRight: true } });
  ok(r);
  const [line] = r.primitives;
  expect(Math.round(line.points[0].x)).toBe(0);
  expect(Math.round(line.points[line.points.length - 1].x)).toBe(vp.width);
  // every point stays inside the clip rect — no geometry outside the domain
  for (const pt of line.points) {
    expect(pt.x).toBeGreaterThanOrEqual(0);
    expect(pt.x).toBeLessThanOrEqual(vp.width);
  }
  // the extended endpoints carry the SAME slope as the anchor segment
  const [g1, g2] = geometryFor('trend', anchors, vp).points;
  const slope = (g2.y - g1.y) / (g2.x - g1.x);
  const [e0, e1] = line.points;
  expect(slope).toBeCloseTo((e1.y - e0.y) / (e1.x - e0.x), 6);
  // and the original anchor points lie ON the extended line
  for (const gp of [g1, g2]) {
    const yOnLine = e0.y + slope * (gp.x - e0.x);
    expect(gp.y).toBeCloseTo(yOnLine, 6);
  }
});

test('no-op extension fields on already-full-span tools are recorded as notes, not pretend-consumed', () => {
  const r = buildPresetRenderSpec({ tool: 'horizontal', anchors: [A(100, 100)], viewport: vp,
    style: { extendLeft: true, extendRight: true } });
  ok(r);
  const note = (r.notes || []).find((n) => n.field === 'extendLeft');
  expect(note).toMatchObject({ scope: 'noop' }); // horizontal already spans the domain
  // the geometry itself is unchanged
  expect(r.primitives[0].points).toEqual(geometryFor('horizontal', [A(100, 100)], vp).points);
});

test('shape: fillOpacity drives the rect fill; 0 and absent both render NO fill (false/zero survive)', () => {
  const base = { tool: 'rectangle', anchors: [A(100, 100), A(300, 95)], viewport: vp };
  const filled = buildPresetRenderSpec({ ...base, style: { color: '#5ec986', fillOpacity: 0.5 } });
  expect(filled.primitives[0].fill).toBe('rgba(94,201,134,0.5)');
  const zero = buildPresetRenderSpec({ ...base, style: { fillOpacity: 0 } });
  expect(zero.primitives[0].fill).toBe('none');
  const absent = buildPresetRenderSpec({ ...base });
  expect(absent.primitives[0].fill).toBe('none'); // today's unfilled rect
});

test('label: fontSize consumes; absent keeps the incumbent 12', () => {
  const styled = buildPresetRenderSpec({ tool: 'text', anchors: [A(100, 100)], viewport: vp,
    style: { color: '#e3c16a', fontSize: 15 } });
  expect(styled.primitives[0].fontSize).toBe(15);
  expect(styled.primitives[0].fill).toBe('#e3c16a');
  const absent = buildPresetRenderSpec({ tool: 'text', anchors: [A(100, 100)], viewport: vp });
  expect(absent.primitives[0].fontSize).toBe(12);
  expect(absent.primitives[0].fill).toBe('#dce8f2'); // today's label fill
});

test('fib default equivalence: absent style renders EXACTLY the incumbent fib (levels, common color, labels, no trendline, no fills)', () => {
  const r = buildPresetRenderSpec({ tool: 'fib', anchors, viewport: vp });
  ok(r);
  const g = geometryFor('fib', anchors, vp);
  const polylines = r.primitives.filter((p) => p.kind === 'polyline');
  const texts = r.primitives.filter((p) => p.kind === 'text');
  expect(polylines).toHaveLength(g.levels.length);          // all seven levels
  expect(texts).toHaveLength(g.levels.length);              // today always labels
  for (let i = 0; i < polylines.length; i++) {
    expect(polylines[i].points).toEqual(g.levels[i].points); // the existing geometry
    expect(polylines[i].stroke).toBe('#7fa6c0');             // the common color
    expect(texts[i].text).toBe(String(g.levels[i].ratio));
  }
  expect(r.primitives.filter((p) => p.kind === 'band')).toHaveLength(0);       // no fills today
  expect(r.primitives.filter((p) => p.meta?.part === 'trendline')).toHaveLength(0);
});

test('fib full family: ratios/levelColors/visibility/labels/trendline/fill consume honestly', () => {
  const style = {
    color: '#111111', width: 2, dash: true,
    ratios: [0, 0.5, 1],
    levelColors: ['#aaaaaa', '#bbbbbb', '#cccccc'],
    showLevels: [true, false, true],   // the middle level is hidden
    fillOpacity: 0.3,
    extensions: true,
    trendline: true,
    labels: false,                     // labels OFF
    logScale: false, reverse: false,
  };
  const r = buildPresetRenderSpec({ tool: 'fib', anchors, viewport: vp, style });
  ok(r);
  const polylines = r.primitives.filter((p) => p.kind === 'polyline');
  const levelLines = polylines.filter((p) => p.meta?.part === 'level');
  expect(levelLines).toHaveLength(2); // the hidden level renders nothing
  // per-level colors — the generic color NEVER overrides them
  expect(levelLines.map((p) => p.stroke)).toEqual(['#aaaaaa', '#cccccc']);
  for (const l of levelLines) { expect(l.strokeWidth).toBe(2); expect(l.dash).toBe('6 3'); }
  // trendline drawn with the GENERIC color only (fib color = trendline color)
  const trendline = polylines.find((p) => p.meta?.part === 'trendline');
  expect(trendline.stroke).toBe('#111111');
  // labels OFF -> no text primitives
  expect(r.primitives.filter((p) => p.kind === 'text')).toHaveLength(0);
  // fills sit BETWEEN consecutive VISIBLE levels
  const bands = r.primitives.filter((p) => p.kind === 'band');
  expect(bands).toHaveLength(1);
  expect(bands[0].meta.between).toEqual([0, 1]); // hidden 0.5 joins its visible neighbors
  expect(bands[0].fill).toBe('rgba(170,170,170,0.3)'); // first visible level's color at the preset opacity
  // extensions: every level line reaches the domain's right edge
  for (const l of levelLines) {
    expect(Math.round(l.points[l.points.length - 1].x)).toBe(vp.width);
  }
});

test('fib ratios compute levels through the EXISTING projection math', () => {
  const style = { ratios: [0, 1] };
  const r = buildPresetRenderSpec({ tool: 'fib', anchors, viewport: vp, style });
  const levelLines = r.primitives.filter((p) => p.meta?.part === 'level');
  const high = Math.max(anchors[0].p, anchors[1].p);
  const low = Math.min(anchors[0].p, anchors[1].p);
  const expectedY = (price) => projectAnchor({ t: anchors[0].t, p: price }, vp).y;
  expect(levelLines[0].points[0].y).toBeCloseTo(expectedY(high), 6); // ratio 0 -> high
  expect(levelLines[1].points[0].y).toBeCloseTo(expectedY(low), 6);  // ratio 1 -> low
});

test('fib reverse mirrors the retracement direction (levels from the opposite extreme)', () => {
  const base = { tool: 'fib', anchors, viewport: vp, style: { ratios: [0, 0.5, 1] } };
  const forward = buildPresetRenderSpec(base);
  const reversed = buildPresetRenderSpec({ ...base, style: { ...base.style, reverse: true } });
  const yOf = (r, i) => r.primitives.filter((p) => p.meta?.part === 'level')[i].points[0].y;
  const high = Math.max(anchors[0].p, anchors[1].p);
  const low = Math.min(anchors[0].p, anchors[1].p);
  expect(yOf(forward, 1)).toBeCloseTo(projectAnchor({ t: anchors[0].t, p: high - (high - low) * 0.5 }, vp).y, 6);
  expect(yOf(reversed, 1)).toBeCloseTo(projectAnchor({ t: anchors[0].t, p: low + (high - low) * 0.5 }, vp).y, 6);
});

test('fib logScale interpolates in log space and REFUSES nonpositive anchors honestly', () => {
  const positive = [A(100, 100), A(300, 105)];
  const r = buildPresetRenderSpec({ tool: 'fib', anchors: positive, viewport: vp,
    style: { ratios: [0, 0.5, 1], logScale: true } });
  ok(r);
  const levelLines = r.primitives.filter((p) => p.meta?.part === 'level');
  const lnHigh = Math.log(105), lnLow = Math.log(100);
  const mid = Math.exp(lnHigh - (lnHigh - lnLow) * 0.5);
  expect(levelLines[1].points[0].y).toBeCloseTo(projectAnchor({ t: positive[0].t, p: mid }, vp).y, 6);
  // a nonpositive anchor is REFUSED — never NaN geometry
  const bad = buildPresetRenderSpec({ tool: 'fib', anchors: [A(100, -5), A(300, 105)], viewport: vp,
    style: { ratios: [0, 0.5, 1], logScale: true } });
  expect(bad.status).toBe('refused');
  expect(bad.reason).toMatch(/log/i);
  expect(bad.primitives).toEqual([]);
  expect(bad.hitGeometry).toBeTruthy(); // the drawing itself stays hit-testable
});

test('risk: semantic role colors survive generic styling; zone alpha consumes fillOpacity; analysis-only label preserved', () => {
  const riskAnchors = [A(100, 100), A(200, 95), A(300, 110)];
  const g = geometryFor('risk', riskAnchors, vp, { side: 'long' });
  const r = buildPresetRenderSpec({ tool: 'risk', anchors: riskAnchors, viewport: vp,
    style: { color: '#ffffff', width: 2, dash: true, fillOpacity: 0.4, side: 'long' } });
  ok(r);
  const roleLines = r.primitives.filter((p) => p.kind === 'polyline');
  expect(roleLines.map((l) => l.stroke)).toEqual(['#e3c16a', '#d65656', '#5ec986']); // role colors preserved — #ffffff never overrides
  for (const l of roleLines) { expect(l.strokeWidth).toBe(2); expect(l.dash).toBe('6 3'); }
  const zones = r.primitives.filter((p) => p.meta?.part === 'zone');
  expect(zones).toHaveLength(2);
  expect(zones[0].fill).toBe('rgba(214,86,86,0.4)'); // stop zone color at the preset alpha
  expect(zones[1].fill).toBe('rgba(94,201,134,0.4)');
  const title = r.primitives.find((p) => p.meta?.part === 'risk-title');
  expect(title.text).toMatch(/analysis only/);          // the honest analysis-only label survives
  // fillOpacity 0 -> no zones at all (zero survives)
  const zero = buildPresetRenderSpec({ tool: 'risk', anchors: riskAnchors, viewport: vp,
    style: { fillOpacity: 0 } });
  expect(zero.primitives.filter((p) => p.meta?.part === 'zone')).toHaveLength(0);
  // absent style -> the incumbent fixed alphas
  const absent = buildPresetRenderSpec({ tool: 'risk', anchors: riskAnchors, viewport: vp });
  expect(absent.primitives.filter((p) => p.meta?.part === 'zone')[0].fill).toBe('rgba(214,86,86,0.14)');
});

test('risk: style.side is the GEOMETRY side input (caller merges the drawing side); absent keeps the default', () => {
  const riskAnchors = [A(100, 100), A(200, 95), A(300, 110)];
  // explicit short side -> the box computes SHORT roles (stop above entry above target)
  const short = buildPresetRenderSpec({ tool: 'risk', anchors: riskAnchors, viewport: vp,
    style: { side: 'short' } });
  ok(short);
  expect(short.primitives.find((p) => p.meta?.part === 'risk-title').text).toMatch(/short/);
  const stopLine = short.primitives.find((p) => p.meta?.part === 'role-line' && p.meta.role === 'stop');
  const entryLine = short.primitives.find((p) => p.meta?.part === 'role-line' && p.meta.role === 'entry');
  expect(stopLine.points[0].y).toBeLessThan(entryLine.points[0].y); // short: stop price ABOVE entry -> smaller y
  // absent side -> the incumbent default 'long'
  const absent = buildPresetRenderSpec({ tool: 'risk', anchors: riskAnchors, viewport: vp });
  expect(absent.primitives.find((p) => p.meta?.part === 'risk-title').text).toMatch(/long/);
});

test('refusals and purity: unsupported tools refuse; inputs are never mutated; the spec is serializable', () => {
  const refused = buildPresetRenderSpec({ tool: 'nope', anchors, viewport: vp });
  expect(refused.status).toBe('refused');
  const style = { color: '#7fa6c0', width: 2 };
  const anchorsCopy = anchors.map((a) => ({ ...a }));
  const vpCopy = { ...vp };
  const r = buildPresetRenderSpec({ tool: 'trend', anchors, viewport: vp, style });
  ok(r);
  expect(anchors).toEqual(anchorsCopy);   // input immutability
  expect(vp).toEqual(vpCopy);
  expect(style).toEqual({ color: '#7fa6c0', width: 2 });
  const serialized = JSON.stringify(r);
  expect(serialized.length).toBeGreaterThan(0);           // fully serializable — no functions
  expect(serialized).not.toMatch(/apiKey|brokerAccount|positions/); // no credentials in a render spec
  expect(r.hitGeometry).toEqual(geometryFor('trend', anchors, vp));  // hit geometry = the original, for drag/selection
});

test('degenerate geometry refuses honestly (no fabricated shapes) and preserves hit geometry', () => {
  const single = buildPresetRenderSpec({ tool: 'fib', anchors: [A(100, 100)], viewport: vp });
  expect(single.status).toBe('refused');
  expect(single.reason).toMatch(/geometry|anchor/i);
  expect(single.primitives).toEqual([]);
});

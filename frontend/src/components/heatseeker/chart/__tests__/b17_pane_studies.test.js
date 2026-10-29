// C118/C121/C124-C126 residuals — the PANE STUDY CONFIGURATION layer (NEW
// pure module, H2's disjoint indicators lease). RED-first: paneStudies.js
// does not exist. ONE ENGINE rule: every number comes from the existing
// primitives (volumeProfile / sma / tpoPeriods / sessionZones / periodKey);
// this layer only validates configuration and derives honest facts.
// Source-gated settings are TYPED REFUSALS, never fake enabled buttons.
import { profileConfig, cvdConfig, tpoConfig } from '../indicators/paneStudies';
import { volumeProfile } from '../indicators/profile';
import { sma } from '../indicators/priceStudies';
import { tpoPeriods } from '../indicators/ProfilePrimitives';

const B = (time, low, high, volume) => ({ time, low, high, volume, open: low, close: high });
const T0 = Date.parse('2026-10-26T13:30:00Z');
const bars = [
  B(T0, 100, 102, 500), B(T0 + 1800000, 101, 103, 700),
  B(T0 + 3600000, 99, 101, 900), B(T0 + 5400000, 100, 104, 800),
];
// the tpoPeriods engine keys periods off NUMERIC (epoch-ms) times — ISO
// strings collapse into one NaN bucket; the config layer refuses them typed.
const ISO_BARS = [
  B('2026-10-26T13:30:00Z', 100, 102, 500), B('2026-10-26T14:00:00Z', 101, 103, 700),
];

test('C121 profileConfig: fixed-200 and visible modes drive the EXISTING engine with honest facts', () => {
  const fixed = profileConfig(bars, { mode: 'fixed-200' });
  expect(fixed.status).toBe('ok');
  expect(fixed.rows).toHaveLength(200);                       // the letter's fixed-200 rows
  expect(fixed.approximation).toBe('bar-range');             // the existing honest label rides
  expect(fixed.facts.totalVolume).toBeCloseTo(2900, 6);         // measured (overlap weighting epsilon ~1e-12)
  expect(Number.isFinite(fixed.facts.poc.price)).toBe(true);
  expect(Number.isFinite(fixed.facts.vah)).toBe(true);       // VAH/VAL derived from the engine's value_area
  expect(Number.isFinite(fixed.facts.val)).toBe(true);
  expect(fixed.facts.vaPct).toBe(0.68);                       // the C121 letter's VA68% default
  expect(fixed.coverage.bars).toBe(4);                        // honest measured window
  const visible = profileConfig(bars, { mode: 'visible' });
  expect(visible.rows).toHaveLength(8);                        // the incumbent visible-window behavior (8-row floor)
  // the engine passthrough is exact: same primitive, same settings
  const direct = volumeProfile(bars, { rows: 200, valueAreaPct: 0.68 });
  expect(fixed.facts.totalVolume).toBeCloseTo(direct.total_volume, 6);
  // bounds refused before any computation
  expect(profileConfig(bars, { mode: 'fixed-200', levels: 5 }).status).toBe('refused');
  expect(profileConfig(bars, { mode: 'nonsense' }).status).toBe('refused');
});

test('C121 profileConfig: a classified buy/sell basis is an explicit HOLD, not a fake setting', () => {
  const out = profileConfig(bars, { mode: 'visible', basis: 'buy' });
  // the bars carry ONLY total volume — per-side basis needs the admitted tape
  expect(out.status).toBe('refused');
  expect(out.reason).toMatch(/classified|tape|source/i);
});

test('C121 profileConfig: bars without volume refuse through the engine\'s typed reason', () => {
  const dry = [B('2026-10-26T13:30:00Z', 100, 102, undefined)];
  const out = profileConfig(dry, { mode: 'visible' });
  expect(out.status).toBe('refused');
  expect(out.reason).toMatch(/volume/i);
});

test('C118 cvdConfig: session anchor + zero-axis rebase + MA smoothing, computed from the REAL estimated path', () => {
  const cvdLine = [
    { time: '2026-10-26T13:30:00Z', cvd: 10 }, { time: '2026-10-26T14:00:00Z', cvd: 25 },
    { time: '2026-10-27T13:30:00Z', cvd: -5 }, { time: '2026-10-27T14:00:00Z', cvd: 3 },
  ];
  const out = cvdConfig(cvdLine, { anchor: 'session', zeroAxis: 'zero-at-anchor', maPeriod: 2 });
  expect(out.status).toBe('ok');
  expect(out.approximation).toBe('estimated-bvc');           // the honest label NEVER becomes a classified claim
  // session rebasing: day 2 restarts at 0, not at day 1's end value
  expect(out.points[2].cvd).toBe(0);
  expect(out.points[3].cvd).toBe(8);                          // -5 -> 3 rebased to 0 -> 8
  // MA smoothing rides the SAME sma primitive — PER contiguous run within one
  // session (the rework rule: the window never crosses an anchor boundary).
  const session1 = sma([0, 15], 2); // day 1 REBASED: 10->0, 25->15
  const session2 = sma([0, 8], 2); // day 2 rebased: -5->0, 3->8
  expect(out.points.map((p) => p.ma)).toEqual([...session1, ...session2]);
  // free zero-axis: no rebasing — the raw path passes through
  const free = cvdConfig(cvdLine, { anchor: 'none', zeroAxis: 'free', maPeriod: 1 });
  expect(free.points.map((p) => p.cvd)).toEqual([10, 25, -5, 3]);
  expect(free.points[0].ma).toBe(10);
  // no finite values -> typed refusal
  expect(cvdConfig([{ time: '2026-10-26T13:30:00Z', cvd: NaN }], { anchor: 'none' }).status).toBe('refused');
  // out-of-bounds MA refused
  expect(cvdConfig(cvdLine, { anchor: 'none', maPeriod: 0 }).status).toBe('refused');
});

test('C124-C126 tpoConfig: bar-resolution periods through the EXISTING engine; tick-true is a TYPED source refusal', () => {
  const out = tpoConfig(bars, { mode: 'bar-resolution', periodMinutes: 30 });
  expect(out.status).toBe('ok');
  expect(out.approximation).toBe('bar-resolution');          // the credited approximation label
  expect(out.periods).toHaveLength(4);                        // 30-min-spaced bars: one period bucket per bar
  expect(out.sessionFacts).toBeTruthy();                      // session high/low facts from sessionZones
  // the engine passthrough is exact
  const direct = tpoPeriods(bars, { periodMinutes: 30 });
  expect(out.periods.length).toBe(direct.periods.length);     // engine passthrough exact
  // TICK-TRUE mode: the admitted trade tape does not exist -> typed refusal, never a fake mode
  const tick = tpoConfig(bars, { mode: 'tick-true' });
  expect(tick.status).toBe('refused');
  expect(tick.reason).toMatch(/tape|source/i);
  // bounds refused
  expect(tpoConfig(bars, { mode: 'bar-resolution', periodMinutes: 0 }).status).toBe('refused');
  // no eligible bars -> the engine's typed reason passes through
  expect(tpoConfig([], { mode: 'bar-resolution' }).status).toBe('refused');
  // ISO-string bar times -> the HONEST typed input refusal (NaN buckets never render)
  const iso = tpoConfig(ISO_BARS, { mode: 'bar-resolution' });
  expect(iso.status).toBe('refused');
  expect(iso.reason).toMatch(/epoch milliseconds/);
});

// --- H3 REWORK vectors (H3-VERDICT-PANESTUDIES-3d65b528-REWORK): explicit
// gaps preserved, MA never bridges a gap or an anchor-period boundary. ---
test('CVD rework: a missing bar stays an explicit hole — never silently dropped, never bridged', () => {
  const cvdLine = [
    { time: '2026-10-26T13:30:00Z', cvd: 10 }, { time: '2026-10-26T14:00:00Z', cvd: 25 },
    { time: '2026-10-26T14:30:00Z', cvd: null }, // the missing bar — must remain a point
    { time: '2026-10-26T15:00:00Z', cvd: 40 },
  ];
  const out = cvdConfig(cvdLine, { anchor: 'none', maPeriod: 2 });
  expect(out.status).toBe('ok');
  expect(out.points).toHaveLength(4);                      // ALL entries render — the hole is not removed
  expect(out.points[2]).toEqual({ time: '2026-10-26T14:30:00Z', cvd: null, ma: null }); // explicit hole
  // the post-gap point's MA is computed from the POST-GAP run only: a single
  // value with maPeriod 2 has no complete window -> null, NOT the average
  // bridged across the missing bar.
  expect(out.points[3].cvd).toBe(40);
  expect(out.points[3].ma).toBe(null);
  // the pre-gap run's MA is untouched by the hole
  expect(out.points[1].ma).toBeCloseTo(17.5, 6);
});

test('CVD rework: MA never carries prior-session values across the anchor boundary', () => {
  const cvdLine = [
    { time: '2026-10-26T14:00:00Z', cvd: 10 }, { time: '2026-10-26T15:00:00Z', cvd: 20 },
    { time: '2026-10-27T14:00:00Z', cvd: 30 }, // a NEW session begins
  ];
  const out = cvdConfig(cvdLine, { anchor: 'session', zeroAxis: 'zero-at-anchor', maPeriod: 2 });
  expect(out.status).toBe('ok');
  // session 2 rebases: 30 - 30 = 0
  expect(out.points[2].cvd).toBe(0);
  // the new session's MA restarts: its first value has no complete window in
  // the NEW session — null, NOT (20 + 30)/2 = 25 carried from session 1.
  expect(out.points[2].ma).toBe(null);
});

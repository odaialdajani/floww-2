import { computeOverview } from '../pulse/overviewBar.js';
import bullish from '../fixtures/overviewPayloads.json';

describe('computeOverview', () => {
  it('bullish: FIR 0.5, Bullish, pc 0.33', () => {
    const p = bullish.find((x) => x.name === 'bullish');
    const ov = computeOverview(p.rows);
    expect(ov.fir).toBeCloseTo(p.expected.fir, 2);
    expect(ov.sessionLabel).toBe(p.expected.sessionLabel);
    expect(ov.pcRatio).toBeCloseTo(p.expected.pcRatio, 2);
    expect(ov.netPremium).toBe(p.expected.netPremium);
  });
  it('bearish', () => {
    const p = bullish.find((x) => x.name === 'bearish');
    const ov = computeOverview(p.rows);
    expect(ov.fir).toBeCloseTo(p.expected.fir, 2);
    expect(ov.sessionLabel).toBe('Bearish');
    expect(ov.netPremium).toBeLessThan(0);
  });
  it('neutral when FIR<0.3', () => {
    const p = bullish.find((x) => x.name === 'neutral');
    const ov = computeOverview(p.rows);
    expect(ov.fir).toBeLessThan(0.3);
    expect(ov.sessionLabel).toBe('Neutral');
  });
  it('empty => fir null, pc null, Neutral', () => {
    const ov = computeOverview([]);
    expect(ov.fir).toBeNull();
    expect(ov.pcRatio).toBeNull();
    expect(ov.sessionLabel).toBe('Neutral');
  });
  it('RVOL honest-empty needs baseline', () => {
    const ov = computeOverview([{ type: 'call', premium: 1e5 }]);
    expect(ov.rvol.state).toBe('needs_baseline');
    expect(ov.rvol.label).toBe('needs baseline');
    expect(ov.rvol.value).toBeNull();
  });
  it('values within ±1% of manual calc', () => {
    const rows = [{ type: 'call', premium: 80000 }, { type: 'put', premium: 20000 }];
    const ov = computeOverview(rows);
    // manual: call 80k put 20k total 100k FIR 0.6 PC 0.25 net 60k Bullish
    expect(ov.fir).toBeCloseTo(0.6, 2);
    expect(ov.pcRatio).toBeCloseTo(0.25, 3);
    expect(ov.netPremium).toBe(60000);
    // within 1% check: computed vs manual same payload => exact here
  });
});

import { markFor, trackerPL, trackerStatus } from './trackerStore.js';

describe('tracker P/L mark priority mid->last->stale', () => {
  it('mid first', () => expect(markFor({}, { mid: 1.2, last: 1.1 })).toBe(1.2));
  it('last fallback', () => expect(markFor({}, { last: 1.1 })).toBe(1.1));
  it('stale when neither', () => expect(markFor({}, {})).toBeNull());
  it('P/L live when both present', () => {
    const e = { type: 'call', entryPrice: 1.0 };
    const { pl, state } = trackerPL(e, { mid: 1.2 });
    expect(state).toBe('live');
    expect(pl).toBeCloseTo(20);
  });
  it('stale when quote missing', () => {
    expect(trackerPL({ type: 'call', entryPrice: 1.0 }, null).state).toBe('stale');
  });
});

describe('trackerStatus proxy', () => {
  it('STILL IN when OI stable', () => expect(trackerStatus({}, { oi: 1000, prevOI: 1000 })).toBe('STILL IN'));
  it('PARTIAL when OI halved', () => expect(trackerStatus({}, { oi: 400, prevOI: 1000 })).toBe('PARTIAL'));
  it('EXITED when OI 0', () => expect(trackerStatus({}, { oi: 0, prevOI: 1000, volume: 10 })).toBe('EXITED'));
  it('UNKNOWN when no oiInfo', () => expect(trackerStatus({}, null)).toBe('UNKNOWN'));
});

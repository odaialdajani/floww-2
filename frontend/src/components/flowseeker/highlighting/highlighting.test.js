import { highlightFlags } from './highlighting.js';
import cases from '../fixtures/highlightingCases.json';

describe('highlightFlags', () => {
  it.each(cases)('$name', ({ row, expected }) => {
    const f = highlightFlags(row);
    expect(f.sizeGtOI).toBe(expected.sizeGtOI);
    expect(f.volGtOI).toBe(expected.volGtOI);
  });
  it('OI=0 and vol>0 => true (not div-by-zero)', () => {
    expect(highlightFlags({ volume: 10, oi: 0 })).toEqual({ sizeGtOI: true, volGtOI: true });
  });
  it('both zero => false', () => {
    expect(highlightFlags({ volume: 0, oi: 0 })).toEqual({ sizeGtOI: false, volGtOI: false });
  });
  it('100% fire rate on defined fixtures', () => {
    // every case with expected true actually fires true
    const trues = cases.filter((c) => c.expected.sizeGtOI);
    for (const c of trues) expect(highlightFlags(c.row).sizeGtOI).toBe(true);
  });
});

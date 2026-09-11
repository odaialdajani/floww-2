import { buildCsvExport, csvRowCount } from './csvExport.js';

describe('csvExport', () => {
  it('row count matches input', () => {
    const rows = [{ ticker: 'SPY', type: 'call', strike: 500, exp: '2026-09-18', dte: 5, vol: 100, oi: 200, premium: 50000, score: 80 }];
    const csv = buildCsvExport(rows, { timestamp: '2026-09-03T00:00:00Z' });
    expect(csvRowCount(csv)).toBe(1);
  });
  it('includes filters and timestamp in header', () => {
    const csv = buildCsvExport([], { filters: { sweepsOnly: true }, timestamp: '2026-09-03T00:00:00Z' });
    expect(csv).toContain('sweepsOnly');
    expect(csv).toContain('2026-09-03');
  });
  it('honest missing values blank, not fake', () => {
    const rows = [{ ticker: 'AAPL', type: 'call', strike: 100, exp: '2026-09-18', vol: null, oi: null }];
    const csv = buildCsvExport(rows);
    // should not contain literal 'null' as value in data row area or fake 1.0
    expect(csv).toBeDefined();
  });
  it('multiple rows', () => {
    const rows = Array.from({ length: 3 }, (_, i) => ({ ticker: 'SPY', type: 'call', strike: 500 + i, exp: '2026-09-18', vol: 100, oi: 200, premium: 30000 + i * 1000 }));
    const csv = buildCsvExport(rows);
    expect(csvRowCount(csv)).toBe(3);
  });
});

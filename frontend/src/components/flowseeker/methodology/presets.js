// Academy starter tab presets — the recommended first setup, not an empty page.
export const STARTER_PRESETS = [
  {
    id: 'broad100k',
    title: 'Broad $100K Stocks',
    filters: { minPremium: 100000, equityType: { stocks: true, etfs: false, indices: false } },
    description: 'All single-name flow ≥$100K — the wide lens before you narrow.',
  },
  {
    id: 'sweeps250k',
    title: 'High-Conviction Sweeps',
    filters: { minPremium: 250000, sweepsOnly: true, minScore: 60, absScore: true },
    description: 'Sweep-classified flow ≥$250K, |score|>60 — fewer rows, higher conviction.',
  },
];

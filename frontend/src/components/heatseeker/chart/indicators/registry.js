// B08 study registry: every study declares inputs/version/source/unit/
// approximation/replay/instance. Bar-VWAP is labelled approximation; tape-exact
// needs classified sizes. No proxy volume without source.
export const STUDIES = {
  sma: { inputs: ['period'], version: 'ma.v1', source: 'ohlc', unit: 'price', approximation: 'none', replay: true },
  ema: { inputs: ['period'], version: 'ma.v1', source: 'ohlc', unit: 'price', approximation: 'none', replay: true },
  vwap: { inputs: ['source', 'bands'], version: 'vwap.v1', source: 'bars', unit: 'price', approximation: 'bar-vwap', replay: true },
  exposureVwap: { inputs: ['scope', 'nodes', 'band', 'envelope'], version: 'gexvwap.v1', source: 'board', unit: 'price', approximation: 'board-weighted', replay: 'cursor-eligible-only' },
};

export function getStudy(name) {
  return STUDIES[name] || null;
}

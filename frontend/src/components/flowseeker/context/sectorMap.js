// Pure JS — no React, no backend. ESM.
export const ETF_SET = new Set([
  'SPY','QQQ','IWM','DIA','TLT','XLF','XLE','XLK','XLV','XLI','XLB','XLU','XLP','XLY',
  'GLD','SLV','USO','UNG','ARKK','SMH','EFA','EEM','VTI','VOO','VEA','VWO','HYG','LQD',
  'XLRE','XLC','IYR','XBI','XOP','GDX','GDXJ','EWZ','FXI','KWEB','SOXL','TQQQ','SQQQ',
  'UVXY','VXX','SPXU','SPXL',
]);

export const INDEX_SET = new Set(['SPX','NDX','RUT','VIX','DJI','SPXW']);

export function equityType(ticker) {
  const t = String(ticker || '').trim().toUpperCase();
  if (!t) return 'stock';
  if (INDEX_SET.has(t)) return 'index';
  if (ETF_SET.has(t)) return 'etf';
  return 'stock';
}

export const SECTOR_MAP = {
  AAPL: 'Technology',
  MSFT: 'Technology',
  NVDA: 'Technology',
  GOOGL: 'Technology',
  GOOG: 'Technology',
  META: 'Technology',
  AMD: 'Technology',
  AVGO: 'Technology',
  ORCL: 'Technology',
  CRM: 'Technology',
  TSLA: 'Consumer Cyclical',
  AMZN: 'Consumer Cyclical',
  HD: 'Consumer Cyclical',
  NKE: 'Consumer Cyclical',
  JPM: 'Financial Services',
  BAC: 'Financial Services',
  GS: 'Financial Services',
  BRK: 'Financial Services',
  JNJ: 'Healthcare',
  UNH: 'Healthcare',
  PFE: 'Healthcare',
  ABBV: 'Healthcare',
  XOM: 'Energy',
  CVX: 'Energy',
};

export function sectorForTicker(ticker) {
  const t = String(ticker || '').trim().toUpperCase();
  return SECTOR_MAP[t] || 'Unknown';
}

// Pure JS — no React, no backend. ESM.
// Re-export from context/sectorMap if available; fallback impl otherwise.
import * as _sectorMap from '../context/sectorMap.js';

const _equityType = _sectorMap && typeof _sectorMap.equityType === 'function' ? _sectorMap.equityType : null;

const ETF_SET_FALLBACK = new Set([
  'SPY','QQQ','IWM','DIA','TLT','XLF','XLE','XLK','XLV','XLI','XLB','XLU','XLP','XLY',
  'GLD','SLV','USO','UNG','ARKK','SMH','EFA','EEM','VTI','VOO','VEA','VWO','HYG','LQD',
  'XLRE','XLC','IYR','XBI','XOP','GDX','GDXJ','EWZ','FXI','KWEB','SOXL','TQQQ','SQQQ',
  'UVXY','VXX','SPXU','SPXL',
]);
const INDEX_SET_FALLBACK = new Set(['SPX','NDX','RUT','VIX','DJI','SPXW']);

function fallback(ticker) {
  const t = String(ticker || '').trim().toUpperCase();
  if (!t) return 'stock';
  if (INDEX_SET_FALLBACK.has(t)) return 'index';
  if (ETF_SET_FALLBACK.has(t)) return 'etf';
  return 'stock';
}

export function equityType(ticker) {
  if (_equityType) return _equityType(ticker);
  return fallback(ticker);
}
export { ETF_SET_FALLBACK as ETF_SET, INDEX_SET_FALLBACK as INDEX_SET };
export const SECTOR_MAP = _sectorMap.SECTOR_MAP || {};
export const sectorForTicker = _sectorMap.sectorForTicker || ((t) => 'Unknown');

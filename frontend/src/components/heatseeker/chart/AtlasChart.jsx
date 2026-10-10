import React from 'react';
import RecordedPriceChart from '../RecordedPriceChart';
import { rankOrbs } from './primitives/ExposureOrbs';
import { sessionVwap } from './indicators/priceStudies';
// Local copy to avoid ESM import in Jest (same string as lightweightAdapter).
const ATTRIBUTION = 'Charting by Lightweight Charts (TradingView, Apache-2.0) — https://www.tradingview.com/';
// Atlas overlay: incumbent SVG candles + orb king + VWAP + flow/dark summary.
// Additive only; RecordedPriceChart and SkylitDashboard untouched. Flag-gated.
export function atlasSummary({ nodes = [], bars = [], flow = null, darkLevels = [] } = {}) {
  const orbs = rankOrbs(nodes);
  const vwap = sessionVwap(bars);
  const lastVwap = [...vwap].reverse().find((r) => r.vwap !== null) || null;
  return {
    king: orbs.king,
    kingReason: orbs.reason,
    vwap: lastVwap?.vwap ?? null,
    flow,
    darkCount: (darkLevels || []).length,
    attribution: ATTRIBUTION,
  };
}
export default function AtlasChart({ ticker, frames, nodes = [], bars = [], flow = null, darkLevels = [], enabled = false }) {
  if (!enabled) {
    return <RecordedPriceChart ticker={ticker} frames={frames} />;
  }
  const summary = atlasSummary({ nodes, bars, flow, darkLevels });
  return (
    <div data-testid="atlas-chart">
      <RecordedPriceChart ticker={ticker} frames={frames} />
      <div data-testid="atlas-orbs">
        {summary.king ? `King ${summary.king.strike} (${summary.king.ratio?.toFixed?.(2) ?? ''})` : `Orbs ${summary.kingReason}`}
      </div>
      <div data-testid="atlas-vwap">{summary.vwap !== null ? `VWAP ${summary.vwap.toFixed(2)}` : 'VWAP unavailable'}</div>
      {flow && <div data-testid="atlas-flow">Flow calls {flow.call_premium} puts {flow.put_premium}</div>}
      <div data-testid="atlas-dark">{summary.darkCount} dark levels</div>
      <small data-testid="atlas-attribution">{summary.attribution}</small>
    </div>
  );
}

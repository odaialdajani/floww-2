import React, { useState } from 'react';
import PriceNodeHistory from '../PriceNodeHistory';
import AtlasChart from './AtlasChart';
// B06 reversible single-pane workspace: controlled open + incumbent fallback.
// No existing controls removed; valid candles carry source age/coverage/partial
// bars, capability reasons and retries. Flag off keeps exact incumbent path.
// B30 Atlas toggle: opt-in overlay (orbs/VWAP/flow) composed on the incumbent,
// default off so existing screens never change unless the user flips it.
export default function ChartWorkspace({ ticker, open = true, useNew = false, onRetry = null, notice = null, frames = null, nodes = [], bars = [], flow = null, darkLevels = [] }) {
  const [atlas, setAtlas] = useState(false);
  if (!useNew) {
    return <PriceNodeHistory ticker={ticker} open={open} />;
  }
  return (
    <div data-testid="chart-workspace" data-ticker={ticker}>
      <button type="button" data-testid="atlas-toggle" aria-pressed={atlas} onClick={() => setAtlas((v) => !v)}>
        {atlas ? 'Hide Atlas overlay' : 'Show Atlas overlay'}
      </button>
      {atlas
        ? <AtlasChart ticker={ticker} frames={frames} nodes={nodes} bars={bars} flow={flow} darkLevels={darkLevels} enabled />
        : <PriceNodeHistory ticker={ticker} open={open} />}
      {notice && <p data-testid="workspace-notice">{notice}</p>}
      {onRetry && <button type="button" onClick={onRetry}>Retry</button>}
    </div>
  );
}

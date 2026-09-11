import React, { useMemo } from 'react';
import { computeOverview } from './overviewBar.js';
import { fmtUSD } from '../scanLogic.js';

// Overview bar v1: Net Premium, P/C ratio, FIR, session label, RVOL honest-empty.
// Every new surface ships loading/empty/stale/error/frozen/honest-missing states.
export default function OverviewBar({ rows, state = 'ready', stale = false }) {
  const ov = useMemo(() => computeOverview(rows), [rows]);

  if (state === 'loading') return <div className="fsb-overview fsb-overview--loading" data-testid="overview-loading">Loading overview…</div>;
  if (state === 'error') return <div className="fsb-overview fsb-overview--error" data-testid="overview-error">Overview unavailable</div>;
  if (state === 'frozen') return <div className="fsb-overview fsb-overview--frozen" data-testid="overview-frozen">Paused</div>;
  if (!rows || rows.length === 0) {
    return (
      <div className="fsb-overview fsb-overview--empty" data-testid="overview-empty">
        <span className="fsb-overview__empty">No flow in window — widen filters or wait for prints</span>
        <span className="fsb-overview__rvol fsb-overview__rvol--needs-baseline" data-testid="rvol-empty">RVOL needs baseline</span>
      </div>
    );
  }

  const firLabel = ov.fir == null ? '—' : ov.fir.toFixed(2);
  const pcLabel = ov.pcRatio == null ? '—' : ov.pcRatio.toFixed(2);
  const leanCls = ov.sessionLabel === 'Bullish' ? 'bull' : ov.sessionLabel === 'Bearish' ? 'bear' : 'neutral';

  return (
    <div className={`fsb-overview${stale ? ' fsb-overview--stale' : ''}`} data-testid="overview-bar">
      {stale && <span className="fsb-overview__stale" data-testid="overview-stale">Stale — retrying</span>}
      <div className="fsb-overview__row">
        <span className="fsb-overview__metric" data-testid="overview-netprem">
          <span className="fsb-overview__label">Net Premium</span>
          <span className="fsb-overview__value">{fmtUSD(ov.netPremium)}</span>
        </span>
        <span className="fsb-overview__metric" data-testid="overview-pc">
          <span className="fsb-overview__label">P/C</span>
          <span className="fsb-overview__value">{pcLabel}</span>
        </span>
        <span className="fsb-overview__metric" data-testid="overview-fir">
          <span className="fsb-overview__label">FIR</span>
          <span className="fsb-overview__value">{firLabel}</span>
        </span>
        <span className={`fsb-overview__metric fsb-overview__metric--lean fsb-overview__metric--${leanCls}`} data-testid="overview-session">
          <span className="fsb-overview__label">Session</span>
          <span className="fsb-overview__value">{ov.sessionLabel}</span>
        </span>
        <span className="fsb-overview__metric fsb-overview__metric--rvol" data-testid="overview-rvol">
          <span className="fsb-overview__label">RVOL</span>
          <span className="fsb-overview__value fsb-overview__value--needs-baseline" title="20-day same-time baseline — building">needs baseline</span>
        </span>
      </div>
    </div>
  );
}

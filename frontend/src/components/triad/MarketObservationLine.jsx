import React, { useEffect, useState } from 'react';
// The MAIN Market context header's observation line (root 09:20 legibility
// defect): the raw snapshot UUID, the full UTC clock and the source string
// move BEHIND a named CLOSED Provenance detail — mirroring the inspector's
// H3-passed ProvenanceLine pattern — so the comparison row reads as one
// calm LIVE/REPLAY · quality · snapshot-generation-age line.
//
// Honesty rules: snapshot age is computed ONLY from the payload's own asof
// against the caller-supplied clock — absent or unparseable asof renders
// NO age (freshness is never invented). It is never called market-observation
// age: that separate clock stays in Provenance. A local timer ages the display
// without a provider request. Every exact field stays reachable
// in the details: the snapshot id, the full UTC clock, the source string,
// the formula, and the market observation clock. This component touches
// NO other clock — market/source/fetch/replay clocks stay where they are.
export default function MarketObservationLine({ replay, data, quality, now = () => Date.now() }) {
  const d = data || {};
  const asofMs = typeof d.asof === 'string' && Number.isFinite(Date.parse(d.asof)) ? Date.parse(d.asof) : null;
  const [, setClockRevision] = useState(0);
  useEffect(() => {
    if (asofMs === null) return undefined;
    const clock = setInterval(() => setClockRevision(value => value + 1), 1000);
    return () => clearInterval(clock);
  }, [asofMs]);
  let age = null;
  let clockAhead = false;
  if (asofMs !== null) {
    const s = Math.floor((now() - asofMs) / 1000);
    clockAhead = s < 0;
    if (s < 60) age = `${s}s ago`;
    else if (s < 3600) age = `${Math.floor(s / 60)}m ago`;
    else if (s < 86400) age = `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m ago`;
    else age = `${Math.floor(s / 86400)}d ago`;
  }
  const label = replay ? 'REPLAY' : 'LIVE';
  const noSnapshot = !d.snapshotId;
  return (
    <div className="tdk-observation" data-testid="triad-source">
      <span className="tdk-observation-line" data-testid="triad-observation-line"
        title={replay ? 'Recorded observation; this is its snapshot-generation age.' : 'Current-reading mode. Use Refresh for another reading; LIVE does not mean a streaming feed.'}>
        {label}
        {noSnapshot ? ' · no snapshot' : ''}
        {` · quality ${quality?.state || 'unknown'}`}
        {clockAhead ? ' · snapshot clock ahead' : age ? ` · snapshot age ${age}` : ''}
      </span>
      <details className="tdk-provenance-details" data-testid="triad-provenance-details">
        <summary title="Exact snapshot identity, formula, source and clocks for this reading">Provenance</summary>
        <dl>
          <dt>Snapshot</dt><dd>{d.snapshotId || 'unknown'}</dd>
          <dt>Generated</dt><dd>{d.asof || 'time unknown'}</dd>
          <dt>Source</dt><dd>{d.data_source || 'unknown'}</dd>
          <dt>Formula</dt><dd>{d.formula_version || d.metrics?.formula_version || 'unknown'}</dd>
          <dt>Market observation</dt><dd>{d.event_time || d.observed_at || 'unknown'}</dd>
        </dl>
      </details>
    </div>
  );
}

export { MarketObservationLine };

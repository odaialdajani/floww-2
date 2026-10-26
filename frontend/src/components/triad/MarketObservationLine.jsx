import React from 'react';
// The MAIN Market context header's observation line (root 09:20 legibility
// defect): the raw snapshot UUID, the full UTC clock and the source string
// move BEHIND a named CLOSED Provenance detail — mirroring the inspector's
// H3-passed ProvenanceLine pattern — so the comparison row reads as one
// calm LIVE/REPLAY · quality · observation-age line.
//
// Honesty rules: the age is computed ONLY from the payload's own asof
// against the caller-supplied clock — absent or unparseable asof renders
// NO age (freshness is never invented). Every exact field stays reachable
// in the details: the snapshot id, the full UTC clock, the source string,
// the formula, and the market observation clock. This component touches
// NO other clock — market/source/fetch/replay clocks stay where they are.
export default function MarketObservationLine({ replay, data, quality, now = () => Date.now() }) {
  const d = data || {};
  const asofMs = typeof d.asof === 'string' && Number.isFinite(Date.parse(d.asof)) ? Date.parse(d.asof) : null;
  let age = null;
  if (asofMs !== null) {
    const s = Math.max(0, Math.floor((now() - asofMs) / 1000));
    if (s < 60) age = `${s}s ago`;
    else if (s < 3600) age = `${Math.floor(s / 60)}m ago`;
    else if (s < 86400) age = `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m ago`;
    else age = `${Math.floor(s / 86400)}d ago`;
  }
  const label = replay ? 'REPLAY' : 'LIVE';
  const noSnapshot = !d.snapshotId;
  return (
    <div className="tdk-observation" data-testid="triad-source">
      <span className="tdk-observation-line" data-testid="triad-observation-line">
        {label}
        {noSnapshot ? ' · no snapshot' : ''}
        {` · quality ${quality?.state || 'unknown'}`}
        {age ? ` · observed ${age}` : ''}
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

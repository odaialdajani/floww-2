import React, {memo, useMemo} from "react";
import "./HeatmapLandmarks.css";

const finite = value => typeof value === "number" && Number.isFinite(value);
const price = value => finite(value) && value > 0;
const money = value => price(value) ? value.toFixed(2) : "Unknown";
const zone = wall => wall ? wall.low === wall.high ? money(wall.low) : `${money(wall.low)}–${money(wall.high)}` : "Unavailable";

// Select existing backend observations only. No gamma calculation, net-sign
// substitution, invented price target, or request to a different data source.
export function readLandmarks(data) {
  const spot = price(data?.spot) ? data.spot : null;
  const basis = data?.exposure_basis || data?.grid?.exposure_basis || null;
  if (basis !== "OI" || data?.quality?.state === "unavailable") return {spot,basis,below:[],above:[],inside:null,call:null,put:null};
  const source = Array.isArray(data?.metrics?.walls) ? data.metrics.walls : [];
  const walls = source.filter(w => typeof w?.wall_id === "string" && price(w.low) && price(w.high) && w.low <= w.high);
  const uniqueWalls = new Set(walls.map(w => w.wall_id)).size === walls.length ? walls : [];
  const below = spot == null ? [] : uniqueWalls.filter(w => w.high < spot).sort((a,b) => b.high - a.high).slice(0,2);
  const above = spot == null ? [] : uniqueWalls.filter(w => w.low > spot).sort((a,b) => a.low - b.low).slice(0,2);
  const inside = spot == null ? null : uniqueWalls.find(w => w.low <= spot && w.high >= spot) || null;
  const strikes = new Set(Array.isArray(data?.grid?.strikes) ? data.grid.strikes.filter(price) : []);
  const rows = (Array.isArray(data?.strikes) ? data.strikes : []).filter(row => price(row?.strike) && strikes.has(row.strike));
  const duplicateRows = new Set(rows.map(row => row.strike)).size !== rows.length;
  const largest = field => {
    if (duplicateRows || !rows.length) return null;
    const measured = rows.filter(row => finite(row[field]) && row[field] >= 0);
    const candidates = measured.filter(row => row[field] > 0).sort((a,b) => b[field] - a[field] || a.strike - b.strike);
    return candidates.length ? {strike:candidates[0].strike, partial:measured.length < rows.length || rows.length < strikes.size || data?.metrics?.raw_missing_oi > 0 || data?.metrics?.raw_invalid > 0 || data?.metrics?.surface_coverage?.raw?.status === "partial"} : null;
  };
  return {spot,basis,below,above,inside,call:largest("call_gex"),put:largest("put_gex")};
}

export function landmarkLabel(read, strike) {
  return [read.call?.strike === strike ? "Call" : null, read.put?.strike === strike ? "Put" : null,
    read.below[0]?.high === strike ? "Below" : null, read.above[0]?.low === strike ? "Above" : null].filter(Boolean).join(" · ");
}

function HeatmapLandmarks({data, reading}) {
  const computed = useMemo(() => reading || readLandmarks(data), [data,reading]);
  const {spot,below,above,inside,call,put} = computed;
  const quality = data?.quality?.state;
  return <section className="heatmap-landmarks" aria-label="Raw OI landmarks">
    <div className="heatmap-landmarks-heading">
      <strong>Raw OI landmarks</strong>
      <span>{data?.replay ? "Recorded map" : "Map reference"} · {spot == null ? "Price unknown" : `$${money(spot)}`}</span>
      <span>{data?.grid?.expiries?.length ?? "Unknown"} loaded expiries · {quality || "quality unknown"}</span>
    </div>
    {computed.basis !== "OI" && <p>Raw OI landmarks unavailable · loaded basis {computed.basis || "unknown"}. Volume is not open interest.</p>}
    <dl className="heatmap-landmarks-levels">
      <div><dt>Support watch · below</dt><dd>{below.length ? below.map(zone).join(" → ") : "Unavailable in loaded scope"}</dd></div>
      <div><dt>Current zone</dt><dd>{zone(inside)}</dd></div>
      <div><dt>Resistance watch · above</dt><dd>{above.length ? above.map(zone).join(" → ") : "Unavailable in loaded scope"}</dd></div>
      <div title="Largest known call-side gamma among loaded strike rows, not the most positive net cell. Missing rows limit the ranking."><dt>Call wall · concentration</dt><dd>{call ? `${money(call.strike)}${call.partial ? " · partial" : ""}` : "Unavailable"}</dd></div>
      <div title="Largest known put-side gamma among loaded strike rows, not the most negative net cell. A put concentration can be above price and is not automatically support."><dt>Put wall · concentration</dt><dd>{put ? `${money(put.strike)}${put.partial ? " · partial" : ""}` : "Unavailable"}</dd></div>
    </dl>
    <p>Zones to watch, not a forecast or entry signal. Hold/reclaim or break/retest needs measured price confirmation. Raw levels stay separate from adjusted cells.</p>
    <details><summary>Level source and time</summary>
      <p>{data?.data_source || "Source unknown"} · {data?.snapshotId || "Snapshot identity unknown"} · {data?.replay ? "recorded observations only" : "current map request"}.</p>
      <p>{data?.event_time || data?.observed_at ? `Market time ${data.event_time || data.observed_at}` : "Market time unknown"} · Snapshot {data?.asof || "time unknown"}. The map reference is not a fresh executable quote.</p>
    </details>
  </section>;
}
export default memo(HeatmapLandmarks);

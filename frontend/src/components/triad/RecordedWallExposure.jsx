import React, { useEffect, useState } from "react";
import axios from "axios";
import { API } from "../../config/api";
import "./RecordedWallExposure.css";

const MEASURES = [
  ["dadgex_net_v1", "Delta-weighted OI · net"],
  ["dadgex_gross_v1", "Delta-weighted OI · gross"],
  ["volume_gamma_v1", "Session volume · net"],
  ["session_delta_volume_gamma_v1", "Session volume × |Δ| · net"],
];
const UNITS = "USD/1% move";
const finite = value => typeof value === "number" && Number.isFinite(value);
const clock = value => typeof value === "string" && /(?:Z|[+-]\d{2}:\d{2})$/i.test(value)
  && Number.isFinite(Date.parse(value)) ? Date.parse(value) : null;
const same = (a, b) => a === b && typeof a === "string" && a.trim().length > 0;
const record = value => value && typeof value === "object" && !Array.isArray(value);
const optionalText = value => value == null || typeof value === "string";

function knownAt(point, cutoff) {
  const event = clock(point.clocks?.event_time), received = clock(point.clocks?.received_at);
  const available = clock(point.clocks?.available_at);
  return event != null && received != null && available != null
    && event <= received && received <= available && available <= cutoff;
}

function recordedScope(saved, ticker, snapshotId, wallId) {
  const row = saved?.snapshot;
  return !saved?.error && same(row?.snapshot_id, snapshotId) && same(row?.ticker, ticker)
    && typeof row?.query_key === "string" && row.query_key.trim()
    && clock(row?.asof_ts) != null && Array.isArray(saved.walls)
    && saved.walls.some(wall => same(wall?.wall_id, wallId)) ? row : null;
}

function matchesSeries(body, anchor, ticker, wallId, metric) {
  const key = body?.series_key;
  return body?.version === "recorded-wall-curve.v1" && body.metric_id === metric
    && same(key?.ticker, ticker) && same(key?.query_key, anchor.query_key)
    && same(key?.wall_id, wallId) && same(key?.metric_id, metric) && key?.units === UNITS
    && Array.isArray(body.points) && body.points.length <= 200
    && (body.gaps == null || Array.isArray(body.gaps) && body.gaps.every(gap => record(gap) && optionalText(gap.reason)))
    && body.points.every(point => record(point) && typeof point.observation_id === "string"
      && ["ok", "partial", "unavailable"].includes(point.status)
      && optionalText(point.source) && optionalText(point.reason)
      && record(point.metric) && point.metric.metric_id === metric && point.metric.units === UNITS
      && record(point.wall) && point.wall.wall_id === wallId
      && record(point.scope) && optionalText(point.scope.formula_version)
      && record(point.clocks) && Object.values(point.clocks).every(optionalText)
      && (point.expiries == null || Array.isArray(point.expiries) && point.expiries.every(value => typeof value === "string")));
}

function curveGeometry(points, cutoff, metric) {
  const admitted = points.map(point => {
    const t = clock(point?.clocks?.event_time);
    return point?.status === "ok" && finite(point.value) && point.metric?.metric_id === metric
      && point.metric?.units === UNITS && knownAt(point, cutoff) ? { point, t, value: point.value } : null;
  });
  const valid = admitted.filter(Boolean);
  if (!valid.length) return { dots: [], lines: [] };
  const minT = Math.min(...valid.map(p => p.t)), maxT = Math.max(...valid.map(p => p.t));
  const low = Math.min(0, ...valid.map(p => p.value)), high = Math.max(0, ...valid.map(p => p.value));
  const position = p => ({ ...p, x: minT === maxT ? 200 : 16 + 368 * ((p.t - minT) / (maxT - minT)),
    y: high === low ? 70 : 124 - 108 * ((p.value - low) / (high - low)) });
  const dots = admitted.map(p => p && position(p));
  const lines = [];
  for (let i = 1; i < dots.length; i += 1) {
    const a = dots[i - 1], b = dots[i];
    if (!a || !b || b.t < a.t || b.point.line?.status !== "continuous") continue;
    // Check both neighbours, even if a malformed response claims continuity.
    if (!["provider", "scope_id", "session_date", "formula_version", "exposure_basis"]
      .every(key => same(a.point.scope?.[key], b.point.scope?.[key]))
      || !same(a.point.wall?.definition_version, b.point.wall?.definition_version)) continue;
    lines.push([a, b]);
  }
  return { dots: dots.filter(Boolean), lines, low, high, minT, maxT };
}

function RecordedResult({ body, cutoff, metric }) {
  const points = body.points;
  const { dots, lines, low, high, minT, maxT } = curveGeometry(points, clock(cutoff), metric);
  const available = body.coverage?.n_points_available;
  return <>
    <p role="status" data-testid="recorded-wall-state">
      {points.length} of {Number.isSafeInteger(available) && available >= points.length ? available : "unknown"} stored observations
      {body.coverage?.truncated === true ? " · result truncated" : ""} · {body.status}
      {body.reason ? ` · ${body.reason}` : ""}
    </p>
    {dots.length ? <svg viewBox="0 0 400 140" role="img" aria-label="Recorded adjusted exposure" data-testid="recorded-wall-chart">
      <title>Recorded adjusted exposure · {UNITS}</title>
      <desc>Recorded market-observation times from {new Date(Math.min(...dots.map(p => p.t))).toISOString()} to {new Date(Math.max(...dots.map(p => p.t))).toISOString()}. Missing, partial and unavailable observations break the line. Values and clocks are listed below.</desc>
      <text x="16" y="11">{high.toLocaleString("en-US")} {UNITS}</text>
      <text x="16" y="138">{low.toLocaleString("en-US")}</text>
      {lines.map(([a, b], i) => <line key={i} data-testid="recorded-wall-segment" x1={a.x} y1={a.y} x2={b.x} y2={b.y} />)}
      {dots.map(({ point, x, y }) => <circle key={point.observation_id} data-testid="recorded-wall-point" cx={x} cy={y} r="3"><title>{point.clocks.event_time} · {point.value} {UNITS} · {point.source}</title></circle>)}
    </svg> : <p>No comparable recorded readings for this measure.</p>}
    {dots.length > 0 && <p className="rwe-note">Market time (New York): {new Date(minT).toLocaleTimeString("en-US", { timeZone: "America/New_York" })} → {new Date(maxT).toLocaleTimeString("en-US", { timeZone: "America/New_York" })}</p>}
    <p className="rwe-note">Stored adjusted exposure · {UNITS}. Gaps break the line. Session volume × |Δ| uses option delta; a negative value is signed exposure.</p>
    {!!body.gaps?.length && <p className="rwe-note">Recorded gaps: {[...new Set(body.gaps.map(gap => gap.reason))].join(" · ")}</p>}
    <details className="rwe-observations">
      <summary>Observation details ({points.length})</summary>
      <ol data-testid="recorded-wall-observations">
        {points.map((point, i) => <li key={`${point.observation_id || "unknown"}-${i}`}>
          <strong>{["ok", "partial"].includes(point.status) && finite(point.value) && knownAt(point, clock(cutoff)) ? `${point.value} ${point.metric?.units || "units unknown"}` : "Unavailable"}</strong>
          <span>{point.status || "unknown"}{point.reason ? ` · ${point.reason}` : ""}</span>
          <span>Source: {point.source || "unknown"} · observation {point.observation_id || "unknown"}</span>
          <span>Market: {point.clocks?.event_time || "unknown"}</span>
          <span>Received: {point.clocks?.received_at || "unknown"} · available: {point.clocks?.available_at || "unknown"}</span>
          <span>Coverage: {["usable", "missing", "invalid", "n_contracts"].map(key => `${Number.isSafeInteger(point.coverage?.[key]) && point.coverage[key] >= 0 ? point.coverage[key] : "unknown"} ${key === "n_contracts" ? "contracts" : key}`).join(" · ")}</span>
          <span>Expiries: {point.expiries?.join(", ") || "unknown"} · formula: {point.scope?.formula_version || "unknown"}</span>
          {point.line?.break_reason && <span>Gap: {point.line.break_reason}</span>}
        </li>)}
      </ol>
    </details>
  </>;
}

export default function RecordedWallExposure({ ticker, snapshotId, wallId, visible }) {
  const [open, setOpen] = useState(false);
  const [metric, setMetric] = useState(MEASURES[0][0]);
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState(null);
  const requestKey = JSON.stringify([ticker, snapshotId, wallId, metric, attempt]);
  useEffect(() => {
    if (!open || !visible) return undefined;
    const controller = new AbortController();
    let current = true;
    const save = value => { if (current) setResult({ key: requestKey, ...value }); };
    save({ state: "loading" });
    (async () => {
      if (!snapshotId || !wallId) { save({ state: "unavailable", reason: "SAVED_SCOPE_UNAVAILABLE" }); return; }
      try {
        const { data: saved } = await axios.get(`${API}/solstice/replay/${encodeURIComponent(snapshotId)}`, { signal: controller.signal, timeout: 15000 });
        if (!current) return;
        const anchor = recordedScope(saved, ticker, snapshotId, wallId);
        if (!anchor) { save({ state: "unavailable", reason: "SAVED_SCOPE_UNAVAILABLE" }); return; }
        const { data: body } = await axios.get(`${API}/solstice/wall-curve/${encodeURIComponent(ticker)}`, {
          signal: controller.signal, timeout: 15000, params: { wall_id: wallId, metric_id: metric, query_key: anchor.query_key, as_of: anchor.asof_ts, limit: 200 },
        });
        if (!current) return;
        if (["unavailable", "error"].includes(body?.status)) save({ state: "unavailable", reason: body.reason || body.error || "RECORDED_READ_UNAVAILABLE" });
        else if (!["ok", "partial"].includes(body?.status) || !matchesSeries(body, anchor, ticker, wallId, metric)) save({ state: "unavailable", reason: "RECORDED_SCOPE_MISMATCH" });
        else save({ state: "ready", body, cutoff: anchor.asof_ts });
      } catch (error) {
        if (current) save({ state: "error", reason: "RECORDED_READ_FAILED" });
      }
    })();
    return () => { current = false; controller.abort(); };
  }, [open, visible, requestKey, ticker, snapshotId, wallId, metric]);
  const shown = result?.key === requestKey ? result : null;
  return <details className="rwe-section" onToggle={event => {
    if (event.target === event.currentTarget) setOpen(event.currentTarget.open);
  }}>
    <summary>Recorded adjusted exposure</summary>
    {open && <div className="rwe-body">
      <label>Measure <select value={metric} onChange={event => setMetric(event.target.value)}>{MEASURES.map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>
      <p className="rwe-note">Through the selected saved snapshot. No saved scope means no history; no current-chain substitute.</p>
      {!shown || shown.state === "loading" ? <p role="status" data-testid="recorded-wall-state">Loading recorded observations…</p>
        : shown.state === "ready" ? <RecordedResult body={shown.body} cutoff={shown.cutoff} metric={metric} />
          : <p role="status" data-testid="recorded-wall-state">Recorded observations unavailable · {shown.reason}</p>}
      {shown?.state === "error" && <button type="button" onClick={() => setAttempt(n => n + 1)}>Retry recorded read</button>}
    </div>}
  </details>;
}

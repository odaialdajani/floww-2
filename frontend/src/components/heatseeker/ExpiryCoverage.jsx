import React, { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import { API } from "../../config/api";

function refusal(data, ticker) {
  if (data?.version !== "coverage-read.v1") return "COVERAGE_VERSION_UNSUPPORTED";
  if (data.ticker !== ticker) return "EXPIRY_IDENTITY_MISMATCH";
  if (data.window?.min_dte !== 14 || data.window?.max_dte !== 60) return "EXPIRY_WINDOW_MISMATCH";
  if (data.stale === true) return "EXPIRY_OBSERVATION_STALE";
  if (data.stale !== false) return "EXPIRY_FRESHNESS_UNKNOWN";
  if (!data.fetched_at || !Number.isFinite(Date.parse(data.fetched_at)) || !data.data_source) return "EXPIRY_OBSERVATION_UNDECLARED";
  if (!Array.isArray(data.expiries) || data.expiries.some(row =>
    typeof row?.expiry !== "string" || !row.expiry || typeof row.admitted !== "boolean" || !row.reason
    || (row.admitted && (!Number.isInteger(row.dte) || row.dte < 14 || row.dte > 60 || row.reason !== "ADMITTED")))
    || data.n_admitted !== data.expiries.filter(row => row.admitted).length) return "EXPIRY_INVENTORY_UNAVAILABLE";
  const coverage = data.coverage;
  if (data.expiries.some(row => row.display_envelope !== undefined && typeof row.display_envelope !== "boolean")) return "EXPIRY_COVERAGE_UNAVAILABLE";
  if (coverage !== undefined && (!coverage || coverage.requested_expiries !== 12
    || coverage.n_listed !== data.expiries.length || coverage.n_listed > 12
    || data.expiries.some(row => typeof row.display_envelope !== "boolean")
    || coverage.n_display_envelope !== data.expiries.filter(row => row.display_envelope).length
    || typeof coverage.listing_capped !== "boolean" || coverage.listing_capped !== (coverage.n_listed === 12)
    || typeof coverage.lower_edge_observed !== "boolean" || typeof coverage.upper_edge_observed !== "boolean")) return "EXPIRY_COVERAGE_UNAVAILABLE";
  const projection = data.range_map;
  if (projection !== undefined) {
    const admitted = data.expiries.filter(row => row.admitted).sort((a, b) => a.dte - b.dte);
    if (!projection || projection.version !== "coverage-read.v1" || projection.window?.min_dte !== 14 || projection.window?.max_dte !== 60
      || !Array.isArray(projection.admitted_expiries) || !Array.isArray(projection.admitted_dtes)
      || projection.admitted_expiries.length !== admitted.length || projection.admitted_dtes.length !== admitted.length
      || admitted.some((row, index) => row.expiry !== projection.admitted_expiries[index] || row.dte !== projection.admitted_dtes[index])
      || projection.min_admitted_dte !== (admitted[0]?.dte ?? null) || projection.max_admitted_dte !== (admitted.at(-1)?.dte ?? null)
      || typeof projection.complete !== "boolean" || (projection.complete ? projection.reason !== null : typeof projection.reason !== "string" || !projection.reason)) return "EXPIRY_PROJECTION_UNAVAILABLE";
  }
  return null;
}

/** Read-only listing admission is not a new observation or a range-map query. */
export default function ExpiryCoverage({ ticker, replay = false }) {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const generation = useRef(0);
  const controller = useRef(null);
  useEffect(() => {
    generation.current += 1;
    controller.current?.abort();
    setResult(null);
    setLoading(false);
    return () => { generation.current += 1; controller.current?.abort(); };
  }, [ticker, replay]);
  const read = useCallback(async () => {
    if (replay) return;
    const id = ++generation.current;
    controller.current?.abort();
    const ctrl = new AbortController();
    controller.current = ctrl;
    setResult(null);
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/solstice/price-paths/expiries?ticker=${encodeURIComponent(ticker)}&min_dte=14&max_dte=60&expirations=12`, { signal: ctrl.signal, timeout: 15000 });
      if (generation.current !== id) return;
      const reason = refusal(data, ticker);
      setResult(reason ? { reason } : { data });
    } catch (error) {
      if (generation.current === id) setResult({ reason: error.response?.data?.error || error.response?.data?.detail?.error || "EXPIRY_READ_FAILED" });
    } finally {
      if (generation.current === id) setLoading(false);
    }
  }, [ticker, replay]);
  return <details className="solstice-expiry-coverage" data-testid="solstice-expiry-coverage">
    <summary>Listed 14–60 DTE coverage</summary>
    <div>
      <p>Read-only admission among the first 12 listed expiries. This is not complete range coverage and does not change the map or selected observation.</p>
      <button type="button" className="skylit-trade-mode-btn" onClick={read} disabled={replay || loading}
        title={replay ? "Historical replay cannot use today's expiry inventory" : loading ? "Waiting for the listed-expiry read" : "Read the current listed-expiry admission; no model or order"}>Read listed coverage</button>
      {replay && <p role="status">Replay: current expiry inventory is unavailable; use recorded dates.</p>}
      {loading && <p role="status">Reading listed expiries…</p>}
      {result?.reason && <p role="status">Coverage unavailable · {result.reason}</p>}
      {result?.data && <>
        <p>{result.data.data_source} · fetched {result.data.fetched_at} · {result.data.n_admitted} admitted in this listing</p>
        {result.data.coverage ? <p role="status">{result.data.coverage.n_listed} returned / {result.data.coverage.requested_expiries} requested · {result.data.coverage.n_display_envelope} within the optional ≤30 DTE filter · {result.data.coverage.listing_capped ? "Listing capped" : "Listing below request limit; completeness unknown"} · {result.data.coverage.lower_edge_observed ? "Lower edge observed" : "Lower edge not observed"} · {result.data.coverage.upper_edge_observed ? "Upper edge observed" : "Upper edge not observed"}. Edge observations do not establish exhaustive coverage.</p> : <p role="status">Coverage metadata unavailable; listing completeness unknown.</p>}
        <p>The ≤30 DTE filter is separate from 14–60 DTE admission. It is not a persisted analytical envelope or a range-map projection.</p>
        {result.data.range_map && <section aria-label="Admitted listing projection" data-testid="solstice-expiry-projection">
          <p>Listed admission projection · {result.data.range_map.min_admitted_dte === null ? "No admitted dates returned" : `${result.data.range_map.min_admitted_dte}–${result.data.range_map.max_admitted_dte} DTE`}</p>
          <p>{result.data.range_map.complete ? "Producer reports complete listing; exhaustive coverage unverified" : `Listing incomplete · ${result.data.range_map.reason}`}. No analytical grid or owning display record; range-map playback remains unavailable.</p>
          <ul>{result.data.range_map.admitted_expiries.map((expiry, index) => <li key={`${expiry}:${index}`}>{expiry} · {result.data.range_map.admitted_dtes[index]} DTE</li>)}</ul>
        </section>}
        {result.data.expiries.length ? <table aria-label="Listed expiry admission">
          <thead><tr><th>Expiry</th><th>DTE</th><th>Admission</th><th>≤30 DTE filter</th></tr></thead>
          <tbody>{result.data.expiries.map((row, index) => <tr key={`${row.expiry}:${index}`}><td>{row.expiry}</td><td>{row.dte == null ? "unknown" : `${row.dte} DTE`}</td><td>{row.reason}</td><td>{row.display_envelope === true ? "Within" : row.display_envelope === false ? "Outside" : "Unknown"}</td></tr>)}</tbody>
        </table> : <p>No expiries returned in this count-limited listing; range absence is not established.</p>}
      </>}
    </div>
  </details>;
}

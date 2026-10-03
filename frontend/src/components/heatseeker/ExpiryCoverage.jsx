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
      if (generation.current === id) setResult({ reason: error.response?.data?.detail?.error || "EXPIRY_READ_FAILED" });
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
        {result.data.expiries.length ? <table aria-label="Listed expiry admission">
          <thead><tr><th>Expiry</th><th>DTE</th><th>Admission</th></tr></thead>
          <tbody>{result.data.expiries.map((row, index) => <tr key={`${row.expiry}:${index}`}><td>{row.expiry}</td><td>{row.dte == null ? "unknown" : `${row.dte} DTE`}</td><td>{row.reason}</td></tr>)}</tbody>
        </table> : <p>No expiries returned in this count-limited listing; range absence is not established.</p>}
      </>}
    </div>
  </details>;
}

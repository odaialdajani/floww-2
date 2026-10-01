import React, { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import { API } from "../../config/api";
import { mutatingHeaders } from "../../utils/appKey";

const STATES = { "not-scanned": "Not scanned — press Scan", "no-eligible-rows": "No eligible rank inputs",
  "partial-budget": "Partial budget — only measured rows ranked", stale: "Stale — prior observations",
  "source-error": "Source error — ranking unavailable", unavailable: "Scan unavailable", partial: "Partial coverage", ready: "Measured research ranking" };

/** Separate Solstice consumer: never changes the legacy Tide leaderboard's endpoint or state. */
export default function SolsticeLeaderboard({ onPick, limit = 12, dte = null, maxExpiries = 2 }) {
  const [body, setBody] = useState(null);
  const [status, setStatus] = useState("Loading leaderboard…");
  const [scanning, setScanning] = useState(false);
  const generation = useRef(0);
  const controller = useRef(null);
  const load = useCallback(async scan => {
    const headers = scan ? mutatingHeaders() : null;
    if (scan && !headers) { setStatus("Authentication required — no scan started"); return; }
    const gen = ++generation.current;
    controller.current?.abort();
    const ctrl = new AbortController();
    controller.current = ctrl;
    setScanning(scan);
    try {
      const params = { limit, max_expiries: maxExpiries, dte };
      const response = scan
        ? await axios.post(`${API}/solstice/scan`, { ...params, refresh: true }, { headers, signal: ctrl.signal, timeout: 120000 })
        : await axios.get(`${API}/solstice/scan/leaderboard`, { params, signal: ctrl.signal, timeout: 15000 });
      if (gen !== generation.current) return;
      setBody(response.data || {});
      setStatus(STATES[response.data?.status] || "Availability unknown");
    } catch (e) {
      if (gen !== generation.current || ctrl.signal.aborted) return;
      setStatus(e?.response?.status === 401 || e?.response?.status === 503
        ? "Scan authentication unavailable — no permission assumed" : "Leaderboard unavailable — retry read");
    } finally { if (gen === generation.current) setScanning(false); }
  }, [limit, dte, maxExpiries]);
  useEffect(() => {
    setBody(null);
    load(false);
    const timer = setInterval(() => load(false), 300000);
    return () => { generation.current++; controller.current?.abort(); clearInterval(timer); };
  }, [load]);
  const rows = (body?.leaderboard || []).filter(r => typeof r.conviction === "number" && Number.isFinite(r.conviction));
  return <section className="panel p-3" data-testid="solstice-leaderboard" aria-label="Solstice research leaderboard">
    <header className="flex items-center justify-between mb-2"><span className="label">Research leaderboard</span>
      <button className="btn" disabled={scanning} onClick={() => load(true)}>{scanning ? "Scanning…" : "Scan"}</button></header>
    <p role="status" className="text-[11px] text-slate-400">{status}</p>
    <p className="text-[10px] text-slate-500">Unvalidated research ranking · not probability · {body?.rank_method || "method pending"}
      {typeof body?.leaderboard_age_s === "number" && Number.isFinite(body.leaderboard_age_s) ? ` · computed ${Math.round(body.leaderboard_age_s)}s ago` : " · age unknown"}</p>
    <div className="flex flex-col gap-1 text-[12px]">{rows.map(r => <button className="flex justify-between text-left" key={r.ticker} onClick={() => onPick?.(r.ticker)}
      title={`Inputs: ${JSON.stringify(r.evidence || {})}; observation ${r.asof || "unknown"}`}>
      <span>#{r.rank ?? "—"} {r.ticker}</span><span>{r.conviction.toFixed(1)} rank points</span></button>)}</div>
    {(body?.availability || []).some(r => r.reason) && <details><summary>Missing inputs / access</summary>
      {(body.availability || []).filter(r => r.reason).map((r, i) => <p key={`${r.ticker}-${i}`}>{r.ticker} · {r.reason}</p>)}</details>}
    <button className="btn text-[10px]" onClick={() => load(false)} disabled={scanning}>Retry read</button>
  </section>;
}

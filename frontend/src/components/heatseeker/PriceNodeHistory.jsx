import React, { lazy, Suspense, useEffect, useMemo, useState } from "react";
import axios from "axios";
import { API } from "../../config/api";
import { priceNodeTraces } from "./priceNodeTraces";

const Plot = lazy(() => import("react-plotly.js"));

export default function PriceNodeHistory({ ticker = "SPY", open: controlledOpen, onOpenChange }) {
  const [localOpen, setLocalOpen] = useState(false);
  const open = controlledOpen ?? localOpen;
  const setOpen = value => { setLocalOpen(value); onOpenChange?.(value); };
  const [days, setDays] = useState(5);
  const [scope, setScope] = useState("");
  const [payload, setPayload] = useState(null);
  const [status, setStatus] = useState("idle");
  const [reload, setReload] = useState(0);
  const [position, setPosition] = useState(0);
  const [playing, setPlaying] = useState(false);
  useEffect(() => { setScope(""); setPayload(null); setPlaying(false); }, [ticker]);
  useEffect(() => {
    if (!open) return undefined;
    const controller = new AbortController();
    let active = true;
    setPayload(null); setStatus("loading"); setPlaying(false);
    axios.get(`${API}/heatseeker/price-history/${encodeURIComponent(ticker)}`, {
      params: { days, ...(scope ? { query_key: scope } : {}) },
      timeout: 30000, signal: controller.signal,
    }).then(({ data }) => {
      if (!active || data?.ticker !== ticker.toUpperCase()) return;
      setPayload(data); setPosition(Math.max(0, (data.frames?.length || 0) - 1)); setStatus("ready");
    }).catch(() => { if (active) setStatus("error"); });
    return () => { active = false; controller.abort(); };
  }, [ticker, days, scope, open, reload]);
  const frames = payload?.ticker === ticker.toUpperCase() ? payload.frames || [] : [];
  useEffect(() => {
    if (!playing || !open || frames.length < 2) return undefined;
    const id = setInterval(() => setPosition(p => {
      if (p >= frames.length - 1) { setPlaying(false); return p; }
      return p + 1;
    }), 250);
    return () => clearInterval(id);
  }, [playing, open, frames.length]);
  const traces = useMemo(() => priceNodeTraces(frames.slice(0, position + 1)), [frames, position]);
  return (
    <section className="panel" style={{ margin: "12px 0", padding: 12 }} data-testid="price-node-history">
      <button type="button" className="skylit-trade-mode-btn" aria-expanded={open}
        onClick={() => { setOpen(!open); setPlaying(false); }}>Price chart + historical nodes</button>
      {open && <>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center", marginTop: 12 }}>
          <strong>{ticker} price history</strong>
          <label>Period <select aria-label="History sessions" value={days} onChange={e => setDays(Number(e.target.value))}>
            <option value={1}>1 session</option><option value={5}>1 week</option><option value={20}>1 month</option>
          </select></label>
          {payload?.scopes?.length > 1 && <label>Saved view <select aria-label="Saved node view" value={scope || payload.query_key || ""}
            onChange={e => setScope(e.target.value)}>{payload.scopes.map((s, i) => <option key={s} value={s}>Saved view {i + 1}</option>)}</select></label>}
          <button className="skylit-trade-mode-btn" onClick={() => setReload(n => n + 1)}>Reload history</button>
        </div>
        {status === "loading" && <p role="status">Loading recorded history...</p>}
        {status === "error" && <p role="alert">History could not be loaded. Try reloading.</p>}
        {status === "ready" && !frames.length && <p>No price candles are available for this period.</p>}
        {!!frames.length && <>
          <p style={{ fontSize: 12, color: "var(--muted, #b6bfd0)" }}>
            {payload.candles_with_recorded_nodes} of {frames.length} candles have saved nodes.
            {payload.bar_seconds ? ` ${payload.bar_seconds / 60}-minute candles.` : ""}
            {" "}Gaps mean no recent saved reading. Times are UTC.
            {payload.node_status === "unavailable" ? " Saved node history is currently unavailable." : ""}
            {payload.records_truncated ? " This period contains more saved readings than can be loaded; use a shorter period." : ""}
          </p>
          <Suspense fallback={<p>Opening chart...</p>}>
            <Plot data={traces} useResizeHandler style={{ width: "100%", height: 420 }}
              config={{ responsive: true, displaylogo: false, scrollZoom: true }}
              layout={{ autosize: true, height: 420, paper_bgcolor: "transparent", plot_bgcolor: "transparent",
                font: { color: "#b6bfd0" }, margin: { t: 20, r: 60, b: 35, l: 15 },
                dragmode: "pan", uirevision: `${ticker}:${days}:${payload.query_key}:${reload}`,
                xaxis: { type: "date", rangeslider: { visible: true, thickness: 0.12 }, gridcolor: "#273144" },
                yaxis: { side: "right", gridcolor: "#273144", fixedrange: false },
                legend: { orientation: "h", y: 1.12 } }} />
          </Suspense>
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <button className="skylit-trade-mode-btn" onClick={() => {
              if (!playing && position >= frames.length - 1) setPosition(0);
              setPlaying(v => !v);
            }}>{playing ? "Pause replay" : "Play replay"}</button>
            <input aria-label="Replay position" type="range" min={0} max={frames.length - 1} value={position}
              onChange={e => { setPosition(Number(e.target.value)); setPlaying(false); }} style={{ flex: 1, minWidth: 160 }} />
            <span style={{ fontSize: 12 }}>{frames[position]?.time.replace("T", " ").replace("+00:00", " UTC")}</span>
            <button className="skylit-trade-mode-btn" onClick={() => { setPosition(frames.length - 1); setPlaying(false); }}>Show all</button>
          </div>
        </>}
      </>}
    </section>
  );
}

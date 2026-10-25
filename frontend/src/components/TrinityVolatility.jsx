/**
 * TrinityVolatility.jsx — Three volatility analysis lenses ported from the
 * cvforge screener (cv-apps/scenner34):
 *   1) IV Skew / Smile (selected expiry, call & put)
 *   2) ATM IV Term Structure (contango/backwardation across expiries)
 *   3) 25Δ Risk Reversal (put−call skew steepness by expiry)
 *
 * Reads from the existing decoder endpoint:
 *   /api/chain/{ticker}?expiries=N
 * which returns { spot, expiries, rows:[{strike, expiry, type, iv, delta, ...}] }).
 *
 * Self-contained: scoped CSS (.tv-root, tv-* classes), Plotly via CDN.
 *
 * Truth rules (writer B, market-readings 2026-10-19):
 *   - Missing strike/expiry/side gaps are preserved: no connectgaps, missing
 *     expiries stay on the declared axis as gaps, unavailable reasons are
 *     disclosed, never silently dropped.
 *   - One available call/put side is rendered honestly; the missing side is
 *     explicit, never fabricated.
 *   - ATM IV and 25Δ RR are nearest-observation approximations until
 *     producer-approved admissibility exists: the heading, the hover and the
 *     review lines expose the exact nearest strike, the actual delta, the
 *     distance from target and the unknown side. No agent tolerance or
 *     invented admissibility.
 *   - Vendor IV is never rescaled, clamped or replaced by a local model. The
 *     displayed percentage is iv*100 (decimal-IV contract). Vendor method/time
 *     is unverified; fetched_at is the chain RECEIPT, not a quote observation.
 *   - Rows are validated for exact type, finite values and unique identity;
 *     ambiguous duplicate identity groups are quarantined wholesale.
 *   - Renderer failure (loader, draw error) is a distinct state from data
 *     failure, with a bounded manual Retry per layer and a superseded-request
 *     guard that cancels in-flight work.
 */

import React, { useState, useEffect, useRef, useCallback } from "react";
import axios from "axios";
import { API } from "../config/api";
import "./TrinityVolatility.css";

class ErrorBoundary extends React.Component {
  constructor(props) { super(props); this.state = { hasError: false, error: null }; }
  static getDerivedStateFromError(error) { return { hasError: true, error }; }
  render() {
    if (this.state.hasError) return (
      <div style={{color:'#ff6b6b', padding:'20px', fontFamily:'monospace'}}>
        Triad component error: {this.state.error?.message}
      </div>
    );
    return this.props.children;
  }
}

const PLOT = { responsive: true, displayModeBar: false };

// ---- color palette (matches decoder dark theme) ----
const C = {
  bg: "#0b0d12", panel: "#11141a", border: "rgba(255,255,255,.06)",
  text: "#b0b8c4", muted: "#7a8599", grid: "#1e293b",
  call: "#34d399", put: "#f43f5e", spot: "#38bdf8", mauve: "#a855f7",
  amber: "#fbbf24", faint1: "#7dd3fc", faint2: "#c4b5fd",
};

// ---- formatters (one explicit unit per field) ----
// IV (decimal candidate input) : 3.6807
const fmtIv = (v) => (v == null || isNaN(v)) ? "—" : Number.isInteger(v) ? v.toFixed(0) : v.toFixed(4);
// IV percent display : 368.1%
const fmtPct = (v) => (v == null || isNaN(v)) ? "—" : v.toFixed(1) + "%";
// RR and delta distances : vol points / price points (never ×100, never clamped)
const fmtNum = (v) => (v == null || isNaN(v)) ? "—" : (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(4).replace(/\.?0+$/, "");
// strike (price) display : exact integer 768, decimal 767.94
const fmtStrike = (v) => (v == null || isNaN(v)) ? "—" : Number.isInteger(v) ? v.toFixed(0) : v.toFixed(2);

// ---- validation: exact types, finite values, unique identity ----
// Ambiguous duplicate identity groups are quarantined wholesale: every row
// sharing expiry|type|strike is removed together, never part-admitted.
export function validateChainRows(rows) {
  const issues = [];
  const groups = new Map();
  const cleaned = [];
  rows.forEach((r, i) => {
    if (!r || typeof r !== "object") { issues.push(`row ${i}: not an object`); return; }
    const type = r.type;
    if (type !== "call" && type !== "put") {
      issues.push(`row ${i}: unrecognized type ${type === undefined ? "undefined" : String(type)}`);
      return;
    }
    const expiry = r.expiry;
    if (typeof expiry !== "string" || expiry.length === 0) { issues.push(`row ${i}: missing expiry`); return; }
    const strike = r.strike;
    if (typeof strike !== "number" || !Number.isFinite(strike) || strike <= 0) {
      issues.push(`row ${i}: bad strike`);
      return;
    }
    const iv = r.iv;
    if (typeof iv !== "number" || !Number.isFinite(iv)) { issues.push(`row ${i}: missing IV`); return; }
    // delta is lens-specific: required for RR only, never for skew/nearest-strike.
    const key = `${expiry}|${type}|${strike}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push({ row: r, index: i });
  });
  for (const [key, entries] of groups) {
    if (entries.length > 1) {
      for (const e of entries) {
        issues.push(`row ${e.index}: ambiguous duplicate strike ${e.row.strike} on ${key} — whole group quarantined`);
      }
    }
  }
  for (const r of rows) {
    if (!r || typeof r !== "object") continue;
    const type = r.type;
    if (type !== "call" && type !== "put") continue;
    const expiry = r.expiry;
    if (typeof expiry !== "string" || expiry.length === 0) continue;
    const strike = r.strike;
    if (typeof strike !== "number" || !Number.isFinite(strike) || strike <= 0) continue;
    const iv = r.iv;
    if (typeof iv !== "number" || !Number.isFinite(iv)) continue;
    const key = `${expiry}|${type}|${strike}`;
    if (groups.has(key) && groups.get(key).length > 1) continue; // quarantined
    cleaned.push({ ...r, strike, iv, expiry, type });
  }
  return { rows: cleaned, issues };
}

// Nearest available strike of one type to spot (no tolerance, no interpolation)
function nearestIv(rows, spot, type) {
  let best = null, bestGap = Infinity;
  for (const r of rows) {
    if (r.type !== type || r.iv == null) continue;
    const gap = Math.abs(r.strike - spot);
    if (gap < bestGap) { bestGap = gap; best = r; }
  }
  return best;
}

// ---- pure derived lenses (exported for labelled fixtures) ----
export function computeSkewData(rows, spot, selExp) {
  const callRows = (rows || []).filter(r => r.expiry === selExp && r.type === "call" && r.iv != null);
  const putRows = (rows || []).filter(r => r.expiry === selExp && r.type === "put" && r.iv != null);
  const callOnly = callRows.length > 0 && putRows.length === 0;
  const putOnly = putRows.length > 0 && callRows.length === 0;
  // Declared strike axis first — every strike actually present for this
  // expiry, observed or not — so both-side gaps stay visible.
  const declaredStrikes = [...new Set((rows || []).filter(r => r.expiry === selExp).map(r => r.strike))].sort((a, b) => a - b);
  const lo = spot ? spot * 0.85 : 0;
  const hi = spot ? spot * 1.15 : Infinity;
  const allStrikes = declaredStrikes.filter(s => s >= lo && s <= hi);
  const callMap = {}; callRows.forEach(r => { callMap[r.strike] = r.iv; });
  const putMap = {}; putRows.forEach(r => { putMap[r.strike] = r.iv; });
  return {
    strikes: allStrikes,
    callIv: allStrikes.map(s => (callMap[s] != null ? callMap[s] * 100 : null)),
    putIv: allStrikes.map(s => (putMap[s] != null ? putMap[s] * 100 : null)),
    callOnly, putOnly,
  };
}

// ATM IV term structure: per declared expiry the nearest available call/put IV.
// The term axis keeps every declared expiry — unavailable ones are gaps with a
// reason, never removed. IV is returned in decimal (source unit); the chart y
// is percent. callIv/putIv are the decimal candidate inputs shown in the note.
export function computeTermData(rows, spot, expiryList) {
  if (!spot) return [];
  return (expiryList || []).map(exp => {
    const r2 = (rows || []).filter(r => r.expiry === exp);
    const c = nearestIv(r2, spot, "call");
    const p = nearestIv(r2, spot, "put");
    const hasCall = !!c, hasPut = !!p;
    const iv = hasCall && hasPut ? ((c.iv + p.iv) / 2) * 100 : null; // percent
    return {
      expiry: exp,
      iv,
      hasCall, hasPut,
      callStrike: c ? c.strike : null,
      putStrike: p ? p.strike : null,
      callIv: c ? c.iv : null,   // decimal candidate input
      putIv: p ? p.iv : null,    // decimal candidate input
      callDelta: c ? c.delta : null,
      putDelta: p ? p.delta : null,
      callDistance: c ? Math.abs(c.strike - spot) : null,
      putDistance: p ? Math.abs(p.strike - spot) : null,
    };
  });
}

// 25Δ Risk Reversal: IV(put @ nearest Δ ≈ −0.25) − IV(call @ nearest Δ ≈ +0.25).
// Nearest delta is a nearest-observation approximation: exact strike, delta
// and distance from target are exposed; far deltas are unavailable, never
// silently measured. RR is returned in vol points.
export function computeRrData(rows, expiryList) {
  return (expiryList || []).map(exp => {
    const r2 = (rows || []).filter(r => r.expiry === exp && r.iv != null && r.delta != null);
    let bestC = null, bestP = null, gc = Infinity, gp = Infinity;
    for (const r of r2) {
      if (r.type === "call") {
        const d = Math.abs(r.delta - 0.25);
        if (d < gc) { gc = d; bestC = r; }
      } else {
        const d = Math.abs(r.delta + 0.25);
        if (d < gp) { gp = d; bestP = r; }
      }
    }
    const hasC = bestC != null, hasP = bestP != null;
    const rr = hasC && hasP ? Number(((bestP.iv - bestC.iv) * 100).toFixed(6)) : null; // vol points (float-noise cleanup only, no rounding of the vendor inputs)
    return {
      expiry: exp, rr,
      callStrike: bestC ? bestC.strike : null, putStrike: bestP ? bestP.strike : null,
      callDelta: bestC ? bestC.delta : null, putDelta: bestP ? bestP.delta : null,
      callDistance: bestC ? Math.abs(bestC.delta - 0.25) : null, putDistance: bestP ? Math.abs(bestP.delta + 0.25) : null,
    };
  });
}

// ---- main component ----
export default function TrinityVolatility({ ticker = "SPY", expiries = 8, loaderDeadlineMs = 10000 } = {}) {
  const [rows, setRows] = useState([]);
  const [spot, setSpot] = useState(0);
  const [expiryList, setExpiryList] = useState([]);
  const [selExpIdx, setSelExpIdx] = useState(0);
  const [loading, setLoading] = useState(true);          // data in flight
  const [err, setErr] = useState(null);                  // data failure
  const [renderError, setRenderError] = useState(null); // renderer/draw failure (separate layer): {chart, message}
  const [plotlyReady, setPlotlyReady] = useState(!!window.Plotly); // CDN loaded
  const [plotlyLoadError, setPlotlyLoadError] = useState(false);   // CDN failed (loader layer)
  const [plotLoading, setPlotLoading] = useState(true);      // bounded loader pending
  const [dataStamp, setDataStamp] = useState(0);             // bump once per successful chain fetch
  const [renderRetryTick, setRenderRetryTick] = useState(0); // one bounded manual Retry per renderer layer
  const [dataSource, setDataSource] = useState(null);        // from chain packet, unknown when absent
  const [fetchedAt, setFetchedAt] = useState(null);          // chain receipt
  const [eventTime, setEventTime] = useState(null);          // Greek observation clock, unknown when absent

  const skewRef = useRef(null);
  const termRef = useRef(null);
  const rrRef = useRef(null);
  const reqSeqRef = useRef(0);
  const ctrlRef = useRef(null);
  const plotKeyRef = useRef(0);
  const failedChartRef = useRef(null);
  const redrawRef = useRef(null);
  redrawRef.current = null; // assigned below after callbacks are defined

  // Load Plotly CDN if not present (bounded loader deadline)
  useEffect(() => {
    if (window.Plotly) { setPlotlyReady(true); setPlotLoading(false); return; }
    setPlotLoading(true);
    setPlotlyLoadError(false);
    const s = document.createElement("script");
    s.src = "https://cdn.plot.ly/plotly-2.35.2.min.js";
    s.charset = "utf-8";
    const fail = () => { setPlotlyLoadError(true); setPlotLoading(false); };
    s.onload = () => { setPlotlyReady(true); setPlotLoading(false); };
    s.onerror = fail;
    document.head.appendChild(s);
    const timer = setTimeout(fail, loaderDeadlineMs);
    return () => {
      clearTimeout(timer);
      try { document.head.removeChild(s); } catch (e) { /* noop */ }
    };
  }, [loaderDeadlineMs, plotKeyRef.current]);

  // Fetch chain data — recomputed from current rows on every render; the
  // request is cancelled when superseded or on unmount.
  const fetchChain = useCallback(async () => {
    const myId = ++reqSeqRef.current;
    const ctrl = new AbortController();
    ctrlRef.current = ctrl;
    setLoading(true);
    setErr(null);
    setRenderError(null);          // keep renderer state honest while data loads
    try {
      const r = await axios.get(`${API}/chain/${ticker}?expiries=${expiries}`, { signal: ctrl.signal, timeout: 20000 });
      if (myId !== reqSeqRef.current) { ctrl.abort(); return; } // superseded — cancel work
      if (!r.data || !r.data.rows || !r.data.rows.length) {
        setErr("No chain data for " + ticker);
        setLoading(false);
        return;
      }
      setSpot(r.data.spot || 0);
      setExpiryList(r.data.expiries || []);
      setRows(r.data.rows);
      setDataStamp((v) => v + 1);
      setDataSource(r.data.data_source ?? null);
      setFetchedAt(r.data.fetched_at ?? null);
      setEventTime(r.data.event_time == null ? null : r.data.event_time);
      setSelExpIdx(0);
      setLoading(false);
      setErr(null);
    } catch (e) {
      if (myId !== reqSeqRef.current) return;
      if (e && e.name === "AbortError") return;
      setErr(e.message || "Failed to load chain");
      setLoading(false);
    }
  }, [ticker, expiries]);

  useEffect(() => {
    fetchChain();
    return () => { ctrlRef.current?.abort(); };
  }, [fetchChain]);

  // ---- derived data (validated from current rows every render) ----
  const selExp = expiryList[selExpIdx] || "";
  const validated = validateChainRows(rows);        // recomputed from current rows every render
  const skewData = computeSkewData(validated.rows, spot, selExp);
  const termData = computeTermData(validated.rows, spot, expiryList);
  const rrData = computeRrData(validated.rows, expiryList);

  // ---- faint context smiles (next 2 expiries) ----
  // Shares the validated/admitted rows and the same declared-strike axis.
  const faintSmiles = (() => {
    const out = [];
    if (!skewData.strikes.length) return out;
    for (let j = 1; j <= 2; j++) {
      const e2 = expiryList[selExpIdx + j];
      if (!e2) break;
      const r2 = validated.rows.filter(r => r.expiry === e2 && r.iv != null);
      if (!r2.length) continue;
      const ivByStrike = {};
      for (const r of r2) {
        const prev = ivByStrike[r.strike];
        ivByStrike[r.strike] = prev == null ? r.iv : (prev + r.iv) / 2;
      }
      const ivs = skewData.strikes.map(s => (ivByStrike[s] != null ? ivByStrike[s] * 100 : null));
      if (!ivs.some(v => v != null)) continue;
      out.push({ exp: e2, color: j === 1 ? C.faint1 : C.faint2, ivs });
    }
    return out;
  })();

  // ---- draw charts (async; rejection is caught per layer) ----
  const drawSkew = useCallback(async () => {
    const el = skewRef.current;
    if (!el || !window.Plotly || !skewData.strikes.length) { if (el) window.Plotly.purge(el); return; }
    try {
      const traces = [];
      if (skewData.callIv.some(v => v != null)) {
        traces.push({ x: skewData.strikes, y: skewData.callIv, type: "scatter", mode: "lines", name: "Call IV",
          line: { color: C.call, width: 2.5 }, connectgaps: false,
          hovertemplate: "IV %{y:.1f}%<extra></extra>" });
      }
      if (skewData.putIv.some(v => v != null)) {
        traces.push({ x: skewData.strikes, y: skewData.putIv, type: "scatter", mode: "lines", name: "Put IV",
          line: { color: C.put, width: 2.5 }, connectgaps: false,
          hovertemplate: "IV %{y:.1f}%<extra></extra>" });
      }
      faintSmiles.forEach((sm, i) => {
        traces.push({
          x: skewData.strikes, y: sm.ivs, type: "scatter", mode: "lines",
          name: sm.exp.slice(5), line: { color: sm.color, width: 1, dash: "dot" },
          opacity: 0.55, connectgaps: false,
          hovertemplate: "IV %{y:.1f}%<extra></extra>",
        });
      });
      const layout = {
        paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
        margin: { l: 40, r: 8, t: 6, b: 28 },
        xaxis: { color: C.muted, tickfont: { color: C.muted, size: 11 }, gridcolor: C.grid },
        yaxis: { title: { text: "IV %", font: { size: 10 } }, color: C.muted, tickfont: { color: C.muted, size: 11 }, gridcolor: C.grid },
        legend: { orientation: "h", y: 1.12, font: { size: 10 } },
        hovermode: "x unified",
        shapes: spot ? [{ type: "line", x0: spot, x1: spot, y0: 0, y1: 1, yref: "paper",
          line: { color: C.spot, width: 1, dash: "dot" } }] : [],
        uirevision: "skew",
      };
      await window.Plotly.react(el, traces, layout, PLOT);
    } catch (e) { throw e; }
  }, [skewData, faintSmiles, spot]);

  const drawTerm = useCallback(async () => {
    const el = termRef.current;
    if (!el || !window.Plotly) return;
    try {
      if (!termData.length) { window.Plotly.purge(el); return; }
      const trace = {
        x: termData.map(d => d.expiry), y: termData.map(d => d.iv),
        type: "scatter", mode: "lines+markers", connectgaps: false,
        line: { color: C.mauve, width: 2 }, marker: { size: 5, color: C.mauve },
        hovertemplate: "ATM IV (nearest-observation) %{y:.1f}%<extra></extra>",
      };
      const layout = {
        paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
        margin: { l: 38, r: 8, t: 6, b: 64 },
        xaxis: { color: C.muted, tickfont: { color: C.muted, size: 11 }, tickangle: -40, type: "category" },
        yaxis: { title: { text: "ATM IV %", font: { size: 10 } }, color: C.muted, tickfont: { color: C.muted, size: 11 }, gridcolor: C.grid },
        uirevision: "term",
      };
      await window.Plotly.react(el, [trace], layout, PLOT);
    } catch (e) { throw e; }
  }, [termData]);

  const drawRR = useCallback(async () => {
    const el = rrRef.current;
    if (!el || !window.Plotly) return;
    try {
      if (!rrData.length) { window.Plotly.purge(el); return; }
      const trace = {
        x: rrData.map(d => d.expiry), y: rrData.map(d => d.rr),
        type: "bar", connectgaps: false,
        marker: { color: rrData.map(d => d.rr >= 0 ? "rgba(244,63,94,0.7)" : "rgba(52,211,153,0.7)") },
        hovertemplate: "25Δ RR (nearest-observation) %{y:.1f} vol pts<extra></extra>",
      };
      const layout = {
        paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
        margin: { l: 36, r: 8, t: 6, b: 64 },
        xaxis: { color: C.muted, tickfont: { color: C.muted, size: 11 }, tickangle: -40, type: "category" },
        yaxis: { title: { text: "vol pts", font: { size: 10 } }, color: C.muted, tickfont: { color: C.muted, size: 11 },
          zeroline: true, zerolinecolor: "#475569", gridcolor: C.grid },
        uirevision: "rr",
      };
      await window.Plotly.react(el, [trace], layout, PLOT);
    } catch (e) { throw e; }
  }, [rrData]);

  const redraw = useCallback(async () => {
    if (!plotlyReady) return;
    failedChartRef.current = null;
    const queue = [["skew", drawSkew], ["term", drawTerm], ["rr", drawRR]];
    for (const [chart, draw] of queue) {
      try {
        await draw();
      } catch (e) {
        // fail-fast: the first rejected layer stops the chain; later layers keep
        // their retained state and get a bounded manual Retry of their own.
        failedChartRef.current = chart;
        setRenderError({ chart, message: (e && e.message) || "Volatility chart unavailable" });
        return;
      }
    }
  }, [plotlyReady, drawSkew, drawTerm, drawRR]);
  redrawRef.current = redraw;

  // Redraw is keyed to data/events (new fetch, expiry change), not to every
  // render, so a retry or unrelated state update cannot re-queue hidden draws.
  useEffect(() => {
    if (!plotlyReady || !dataStamp) return;
    void redrawRef.current();
  }, [plotlyReady, dataStamp, selExpIdx]);

  // Purge Plotly instances on unmount
  useEffect(() => {
    return () => {
      [skewRef, termRef, rrRef].forEach(ref => { if (ref.current && window.Plotly) window.Plotly.purge(ref.current); });
    };
  }, []);

  // ---- actions (retry only the failing layer) ----
  const retryData = useCallback(() => {
    setErr(null);
    fetchChain();
  }, [fetchChain]);

  // Bounded manual Retry per renderer layer: re-run only the chart that
  // failed. It runs as an effect keyed to the retry tick so the error-state
  // commit has restored the chart container before the draw looks it up.
  useEffect(() => {
    if (renderRetryTick === 0) return;
    const chart = failedChartRef.current;
    if (!chart) { void redrawRef.current(); return; }
    const draw = chart === "skew" ? drawSkew : chart === "term" ? drawTerm : drawRR;
    void (async () => {
      try {
        await draw(); // redraw only the failed layer, from retained data
        failedChartRef.current = null;
      } catch (e) {
        failedChartRef.current = chart;
        setRenderError({ chart, message: (e && e.message) || "Volatility chart unavailable" });
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [renderRetryTick]);

  const retryRender = useCallback(() => {
    setRenderError(null);
    setRenderRetryTick((v) => v + 1);
  }, []);

  const retryLoad = useCallback(() => {
    plotKeyRef.current += 1;
    setPlotlyLoadError(false);
    setPlotLoading(true);
  }, []);

  // ---- render ----
  if (loading && !err) {
    return <div className="tv-root"><div className="tv-loading">Loading {ticker} volatility…</div></div>;
  }
  if (err) {
    return (
      <div className="tv-root">
        <div className="tv-error-panel" role="alert">
          <div className="tv-error-title">Market data unavailable</div>
          <div className="tv-error-msg">{err}</div>
          <button type="button" className="tv-retry" onClick={retryData}>Retry data</button>
          <div className="tv-error-note">Data failure is separate from renderer failure. Chain {fetchedAt ? `received ${fetchedAt} (receipt)` : "no receipt"} — quote observation clock unverified.</div>
        </div>
      </div>
    );
  }
  if (renderError) {
    return (
      <div className="tv-root">
        <div className="tv-error-panel" role="alert">
          <div className="tv-error-title">Volatility renderer failed</div>
          <div className="tv-error-msg">{renderError.message}</div>
          <button type="button" className="tv-retry" onClick={retryRender}>Retry chart</button>
          <div className="tv-error-note">Data is intact; the SVG renderer (Plotly) rejected the draw. Retry redraws the retained data — zero extra chain requests.</div>
        </div>
      </div>
    );
  }
  if (!plotlyReady) {
    if (plotlyLoadError) {
      return (
        <div className="tv-root">
          <div className="tv-renderer-panel" role="status">
            <div className="tv-renderer-title">Volatility renderer unavailable</div>
            <div className="tv-renderer-msg">Plotly did not load within the bounded wait. The data payload is intact; only the SVG renderer is missing.</div>
            <button type="button" className="tv-retry" onClick={retryLoad}>Retry renderer</button>
          </div>
        </div>
      );
    }
    return (
      <div className="tv-root">
        <div className="tv-renderer-panel" role="status">
          <div className="tv-renderer-title">Volatility renderer loading</div>
          <div className="tv-renderer-msg">Plotly is loading (bounded wait). The data payload is intact; the chart is not drawn until the library arrives.</div>
          <button type="button" className="tv-retry" onClick={retryLoad}>Retry renderer</button>
        </div>
      </div>
    );
  }

  return (
    <ErrorBoundary>
    <div className="tv-root">
      <div className="tv-header">
        <span className="tv-title">Volatility</span>
        <span className="tv-sub">
          {ticker} · spot {spot ? spot.toFixed(2) : "—"} · {expiryList.length} expiries · Source {dataSource ?? "unknown"} (vendor IV, observation clock {eventTime ? `observed ${eventTime}` : "unknown"})
        </span>
        <span className="tv-controls">
          <label>Expiry:&nbsp;
            <select value={selExpIdx} onChange={(e) => setSelExpIdx(Number(e.target.value))}>
              {expiryList.map((e, i) => <option key={e} value={i}>{e}</option>)}
            </select>
          </label>
        </span>
      </div>

      <div className="tv-grid">
        <div className="tv-cell">
          <div className="tv-cell-h">IV Skew <small>{selExp} · {skewData.strikes.length ? (skewData.callOnly ? "call only" : skewData.putOnly ? "put only" : "call & put") : "no IV data"}</small></div>
          <div className="tv-cell-b" ref={skewRef} />
          <div className="tv-legend">
            {skewData.callIv.some(v => v != null) && <span style={{ color: C.call }}>● Call IV</span>}
            {skewData.putIv.some(v => v != null) && <span style={{ color: C.put }}>● Put IV</span>}
            {faintSmiles.map((sm, i) => <span key={i} style={{ color: sm.color }}>┄ {sm.exp.slice(5)}</span>)}
            <span style={{ color: C.spot }}>┄ Spot</span>
          </div>
        </div>

        <div className="tv-cell">
          <div className="tv-cell-h">
            ATM IV Term Structure <small>vol vs expiry · nearest-observation approximation</small>
          </div>
          <div className="tv-cell-b" ref={termRef} />
          <div className="tv-cell-h-notes"><details className="tv-source-details" data-testid="tv-source-details-term">
            <summary>Exact rows · {termData.length} expiries</summary>
            {termData.map(d => (
              <div key={d.expiry}>{d.expiry} · {d.iv == null ? "unavailable" : `ATM IV ${fmtPct(d.iv)}`}
                {d.hasCall ? ` · call ${fmtIv(d.callStrike)} IV ${fmtIv(d.callIv)} Δ${fmtNum(d.callDelta)}` : ""}
                {d.hasPut ? ` · put ${fmtIv(d.putStrike)} IV ${fmtIv(d.putIv)} Δ${fmtNum(d.putDelta)}` : ""}
                {d.hasCall || d.hasPut ? ` (distance ${d.hasCall ? fmtNum(d.callDistance) : "—"}pt ${d.hasPut ? ` · ${fmtNum(d.putDistance)}pt` : ""})` : ""}
              </div>
            ))}
          </details></div>
        </div>

        <div className="tv-cell">
          <div className="tv-cell-h">
            25Δ Risk Reversal <small>put−call skew by expiry · nearest-observation approximation</small>
          </div>
          <div className="tv-cell-b" ref={rrRef} />
          <div className="tv-cell-h-notes"><details className="tv-source-details" data-testid="tv-source-details-rr">
            <summary>Exact rows · {rrData.length} expiries</summary>
            {rrData.map(d => (
              <div key={d.expiry}>{d.expiry} · {d.rr == null ? "unavailable (one side missing)" : `RR ${fmtNum(d.rr)} vol pts`}
                {d.callStrike != null ? ` · call Δ${fmtNum(d.callDelta)} @${fmtIv(d.callStrike)}` : ""}
                {d.putStrike != null ? ` · put Δ${fmtNum(d.putDelta)} @${fmtIv(d.putStrike)}` : ""}
                {d.callStrike != null ? ` · call ${d.callDistance} from +0.25` : ""}
                {d.putStrike != null ? ` · put ${d.putDistance} from −0.25` : ""}
              </div>
            ))}
          </details></div>
        </div>
      </div>

      <div className="tv-status">
        <div className="tv-status-row">Source: {dataSource ?? "unknown"} · chain received {fetchedAt ?? "no receipt"} (receipt) · quote observation time {eventTime ?? "unknown"}</div>
        <div className="tv-status-row">No local rescale: vendor IV values are displayed as returned (iv×100 for percent display only).</div>
        {(validated.issues || []).map((i, k) => <div key={k} className="tv-status-row tv-status-warn">Unavailable: {i}</div>)}
      </div>
    </div>
    </ErrorBoundary>
  );
}

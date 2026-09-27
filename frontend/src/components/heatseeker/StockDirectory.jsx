import React, { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import axios from "axios";
import { API } from "../../config/api";

const buttonStyle = { padding: "7px 10px", border: "1px solid #384254", borderRadius: 5, background: "#172031", color: "#e2e8f0", cursor: "pointer" };

export default function StockDirectory({ onSelect, buttonClass = "skylit-ticker-btn" }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [optionsOnly, setOptionsOnly] = useState(false);
  const [result, setResult] = useState(null);
  const [state, setState] = useState("idle");
  const [attempt, setAttempt] = useState(0);
  const dialogRef = useRef(null);
  const titleId = useId();
  const descriptionId = useId();
  useEffect(() => {
    if (!open || !dialogRef.current) return undefined;
    const dialog = dialogRef.current;
    const priorFocus = document.activeElement;
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
    return () => {
      if (typeof dialog.close === "function" && dialog.open) dialog.close();
      priorFocus?.focus?.();
    };
  }, [open]);
  useEffect(() => {
    if (!open) return undefined;
    const controller = new AbortController();
    let active = true;
    setState("loading");
    const timer = setTimeout(() => {
      axios.get(`${API}/market/catalog`, { params: { page, limit: 100, q: query, options_only: optionsOnly },
        signal: controller.signal, timeout: 30000 }).then(({ data }) => {
        if (active) { setResult(data); setState("ready"); }
      }).catch(() => { if (active) setState("error"); });
    }, 150);
    return () => { active = false; clearTimeout(timer); controller.abort(); };
  }, [open, query, page, optionsOnly, attempt]);
  return <>
    <button type="button" className={buttonClass} onClick={() => setOpen(true)}>Browse all stocks</button>
    {open && createPortal(<>
      <style>{"dialog.floww-stock-directory::backdrop { background: #0009; }"}</style>
      <dialog ref={dialogRef} className="floww-stock-directory" onCancel={() => setOpen(false)} aria-labelledby={titleId} aria-describedby={descriptionId}
        style={{ position: "fixed", top: "50%", left: "50%", margin: 0, transform: "translate(-50%, -50%)",
        boxSizing: "border-box", width: "min(740px, 94vw)", maxHeight: "88vh", overflow: "auto", background: "#101722", color: "#e2e8f0",
        padding: 22, borderRadius: 10, border: "1px solid #384254", zIndex: 10001 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h2 id={titleId} style={{ fontSize: 18, margin: 0 }}>Stocks and funds</h2>
          <button style={buttonStyle} aria-label="Close stock directory" onClick={() => setOpen(false)}>Close</button>
        </div>
        <p id={descriptionId} style={{ color: "#b6bfd0", fontSize: 13 }}>
          Browse your provider's full stock and fund list. Selecting a name opens its data.
          Automatic scan coverage is shown separately in the scanner.
        </p>
        <div style={{ display: "flex", gap: 14, flexWrap: "wrap", margin: "16px 0" }}>
          <input aria-label="Search full stock list" placeholder="Search a ticker" value={query}
            onChange={e => { setQuery(e.target.value); setPage(1); }}
            style={{ ...buttonStyle, cursor: "text", flex: 1, minWidth: 150 }} />
          <label style={{ alignSelf: "center", fontSize: 13 }}><input type="checkbox" checked={optionsOnly}
            onChange={e => { setOptionsOnly(e.target.checked); setPage(1); }} /> Options enabled</label>
        </div>
        {state === "loading" && <p role="status">Loading stocks...</p>}
        {state === "error" && <p role="alert">The stock list could not be loaded. <button style={buttonStyle} onClick={() => setAttempt(v => v + 1)}>Retry</button></p>}
        {state === "ready" && <>
          <p style={{ fontSize: 13 }}>{result.total?.toLocaleString()} available stocks and funds
            {" · "}{result.optionable_total?.toLocaleString()} with options enabled by the provider
            {result.stale ? " · Saved list; refresh unavailable" : ""}</p>
          {!result.complete_provider_catalog && <p role="alert">The full provider list is unavailable.</p>}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))", gap: 7 }}>
            {(result.instruments || []).map(item => <button key={item.symbol} style={buttonStyle}
              onClick={() => { onSelect?.(item.symbol); setOpen(false); }} title={item.options ? "Provider permits option requests; chain availability varies" : "Stock data"}>{item.symbol}</button>)}
          </div>
          {result.matches === 0 && <p>No matching stocks.</p>}
          <div style={{ display: "flex", gap: 12, alignItems: "center", justifyContent: "space-between", marginTop: 16 }}>
            <button style={buttonStyle} disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Previous</button>
            <span style={{ fontSize: 13 }}>Page {page} of {Math.max(1, Math.ceil(result.matches / 100))}</span>
            <button style={buttonStyle} disabled={!result.has_more} onClick={() => setPage(p => p + 1)}>Next</button>
          </div>
        </>}
      </dialog>
    </>, document.body)}
  </>;
}

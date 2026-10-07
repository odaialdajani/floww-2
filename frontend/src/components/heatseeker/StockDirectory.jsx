import React, { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import axios from "axios";
import { API } from "../../config/api";

const buttonStyle = { padding: "7px 10px", border: "1px solid #384254", borderRadius: 5, background: "#172031", color: "#e2e8f0", cursor: "pointer" };

function checkedListTime(rawTime) {
  if (typeof rawTime !== "string" || rawTime.length > 128) return null;
  const parts = /^(\d{4})-(\d{2})-(\d{2})T(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d(?:\.\d{1,9})?)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/.exec(rawTime);
  if (!parts) return null;
  const calendar = new Date(0);
  calendar.setUTCFullYear(Number(parts[1]), Number(parts[2])-1, Number(parts[3]));
  if (calendar.getUTCFullYear() !== Number(parts[1]) || calendar.getUTCMonth()+1 !== Number(parts[2]) || calendar.getUTCDate() !== Number(parts[3])) return null;
  const stamp = Date.parse(rawTime);
  return Number.isFinite(stamp) && stamp <= Date.now()
    ? new Date(stamp).toLocaleString("en-US", { timeZone: "America/New_York" }) : null;
}

export default function StockDirectory({ onSelect, buttonClass = "skylit-ticker-btn", open: controlledOpen, onOpenChange, showTrigger = true, returnFocusRef }) {
  const [localOpen, setLocalOpen] = useState(false);
  const controlled = typeof controlledOpen === "boolean";
  const open = controlled ? controlledOpen : localOpen;
  const setOpen = next => { if (!controlled) setLocalOpen(next); onOpenChange?.(next); };
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
    const priorFocus = returnFocusRef?.current || document.activeElement;
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
    return () => {
      if (typeof dialog.close === "function" && dialog.open) dialog.close();
      if (priorFocus?.isConnected) priorFocus.focus?.();
    };
  }, [open, returnFocusRef]);
  useEffect(() => {
    if (!open) return undefined;
    const controller = new AbortController();
    let active = true;
    setState("loading");
    const timer = setTimeout(() => {
      axios.get(`${API}/market/catalog`, { params: { page, limit: 100, q: query, options_only: optionsOnly },
        signal: controller.signal, timeout: 30000 }).then(({ data }) => {
        if (active) {
          if (!Array.isArray(data?.instruments) || data.instruments.length > 100 || !Number.isSafeInteger(data.matches) || data.matches < data.instruments.length
            || data.instruments.some(item => typeof item?.symbol !== "string" || !/^[A-Z][A-Z0-9.\-]{0,11}$/.test(item.symbol) || optionsOnly && item.options !== true)
            || data.total != null && (!Number.isSafeInteger(data.total) || data.total < 0)
            || data.optionable_total != null && (!Number.isSafeInteger(data.optionable_total) || data.optionable_total < 0 || data.total != null && data.optionable_total > data.total)
            || typeof data.has_more !== "boolean" || data.has_more !== (data.matches > page*100)
            || data.page != null && data.page !== page || data.limit != null && data.limit !== 100) throw Error("Invalid provider directory");
          setResult(data); setState("ready");
        }
      }).catch(() => { if (active) setState("error"); });
    }, 150);
    return () => { active = false; clearTimeout(timer); controller.abort(); };
  }, [open, query, page, optionsOnly, attempt]);
  const listTime = checkedListTime(result?.asof);
  return <>
    {showTrigger && <button type="button" className={buttonClass} onClick={() => setOpen(true)}>Browse all stocks</button>}
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
          <p style={{ fontSize: 13 }}>{Number.isSafeInteger(result.total) ? result.total.toLocaleString() + " available stocks and funds" : "Stock count unknown"}
            {" · "}{Number.isSafeInteger(result.optionable_total) ? result.optionable_total.toLocaleString() + " with options enabled by the provider" : "Options count unknown"}
            {result.stale ? " · Saved list; refresh unavailable" : ""}</p>
          <p style={{ fontSize: 12, color: "#b6bfd0" }}>{listTime ? "List time: " + listTime + " New York" : "List time unknown"}</p>
          {!result.complete_provider_catalog && <p role="alert">The full provider list is unavailable.</p>}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))", gap: 7 }}>
            {(result.instruments || []).map(item => <button key={item.symbol} style={buttonStyle}
              onClick={() => { onSelect?.(item.symbol); setOpen(false); }} title={item.options ? "Provider permits option requests; chain availability varies" : "Stock data"}>{item.symbol}</button>)}
          </div>
          {result.matches === 0 && result.complete_provider_catalog === true && !result.stale && <p>No matching stocks.</p>}
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

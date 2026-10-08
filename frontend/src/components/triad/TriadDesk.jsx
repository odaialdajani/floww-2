import React, { useCallback, useEffect, useRef, useState } from "react";
import { API } from "../../config/api";
import TriadExposure from "./TriadExposure";
import TriadChainTable from "./TriadChainTable";

/**
 * TriadDesk — same-day wall desk (0DTE scope + next-listed fallback).
 *
 * Data comes ONLY from admitted read endpoints: the expiries scope query
 * (0DTE detection), the chain endpoint (quotes/Greeks/annotated exposure
 * per row), and per-row gex basis flags (measured vs unknown). No
 * envelope, no map data, no invented rows. Scope with no same-day series
 * renders the empty panel with a next-listed action (never an empty grid
 * masquerading as data); SPX names the entitlement check explicitly.
 * Nothing here submits, approves, or routes orders — review-only by
 * construction (no order API is referenced anywhere in this file).
 */
const expiriesUrl = ticker =>
  `${API}/solstice/price-paths/expiries?ticker=${encodeURIComponent(ticker)}&min_dte=0&max_dte=7&expirations=12`;
const chainUrl = (ticker, expiry) =>
  `${API}/public/chain/${encodeURIComponent(ticker)}?expiration=${encodeURIComponent(expiry)}&expirations=4`;

function admittedExposure(chain, ticker, expiry) {
  const series = chain?.exposure_by_strike;
  if (!series || series.series_version !== 'triad-projection.backend.v1'
    || series.formula_version !== 'gex.v2' || series.ticker !== ticker
    || series.fetched_at !== chain.fetched_at || series.spot !== chain.spot
    || !Array.isArray(series.strikes)) return null;
  const seen = new Set();
  for (const row of series.strikes) {
    if (!row || !Number.isFinite(row.strike) || row.strike <= 0 || seen.has(row.strike)
      || !Array.isArray(row.expiries) || row.expiries.length !== 1 || row.expiries[0] !== expiry
      || !Number.isInteger(row.n_measured) || !Number.isInteger(row.n_total)
      || row.n_total <= 0 || row.n_measured < 0 || row.n_measured > row.n_total
      || row.partial !== (row.n_measured > 0 && row.n_measured < row.n_total)
      || (row.n_measured > 0 ? !Number.isFinite(row.gex) : row.gex !== null)
      || row.gex_basis !== (row.partial ? 'OI_PARTIAL' : row.n_measured ? 'OI' : 'OI_UNKNOWN')) return null;
    seen.add(row.strike);
  }
  return series;
}

export default function TriadDesk({ ticker }) {
  const [scope, setScope] = useState("0dte");
  const [expiry, setExpiry] = useState(null);
  const [expiriesNote, setExpiriesNote] = useState(null);
  const [chain, setChain] = useState(null);
  const [chainError, setChainError] = useState(null);
  const [selection, setSelection] = useState(null);
  const [copyStatus, setCopyStatus] = useState(null);
  const gen = useRef(0);
  const controllers = useRef([]);

  const beginRequest = useCallback(() => {
    const ctrl = new AbortController();
    controllers.current.push(ctrl);
    return ctrl;
  }, []);
  const resetRequests = useCallback(() => {
    gen.current += 1;
    controllers.current.forEach(c => { try { c.abort(); } catch (e) { /* noop */ } });
    controllers.current = [];
  }, []);

  useEffect(() => {
    setExpiry(null); setChain(null); setChainError(null);
    setSelection(null); setExpiriesNote(null); setCopyStatus(null);
    return () => { resetRequests(); };
  }, [ticker, resetRequests]);

  useEffect(() => {
    let alive = true;
    const myGen = ++gen.current;
    const ctrl = beginRequest();
    setChain(null); setChainError(null); setSelection(null);
    (async () => {
      try {
        const er = await fetch(expiriesUrl(ticker), { signal: ctrl.signal });
        if (!er.ok) throw new Error(`expiries HTTP ${er.status}`);
        const listed = await er.json();
        if (!alive || gen.current !== myGen) return;
        const rows = Array.isArray(listed?.expiries) ? listed.expiries : [];
        const sameDay = rows.filter(r => r && r.dte === 0 && r.admitted);
        if (scope === "0dte" && !sameDay.length) {
          setExpiry(null);
          setExpiriesNote(ticker.startsWith("^")
            ? "Index-option entitlement and the actual listed series need verification."
            : "No same-day series listed for this symbol in this window.");
          return;
        }
        const picked = scope === "0dte"
          ? sameDay.slice().sort((a, b) => (a.expiry < b.expiry ? -1 : 1))[0].expiry
          : (() => {
              const dteByExpiry = new Map(
                rows.filter(r => r && r.expiry != null).map(r => [r.expiry, r.dte]),
              );
              const admittedFuture = (listed?.range_map?.admitted_expiries || [])
                .filter(e => {
                  const d = dteByExpiry.get(e);
                  return typeof d === "number" ? d > 0 : false;
                });
              if (admittedFuture.length) return admittedFuture[0];
              return rows.filter(r => r && r.admitted && typeof r.dte === "number" && r.dte > 0).slice()
                .sort((a, b) => a.dte - b.dte)[0]?.expiry || null;
            })();
        if (!picked) {
          setExpiry(null);
          setExpiriesNote("No admitted expiries in this scope and window.");
          return;
        }
        setExpiriesNote(null);
        setExpiry(picked);
        const cr = await fetch(chainUrl(ticker, picked), { signal: ctrl.signal });
        if (!cr.ok) throw new Error(`chain HTTP ${cr.status}`);
        const body = await cr.json();
        if (!alive || gen.current !== myGen) return;
        setChain(body);
      } catch (e) {
        if (!alive || gen.current !== myGen) return;
        if (e?.name === "AbortError") return;
        setChainError(e.message || "Triad scope read failed");
      }
    })();
    return () => { alive = false; };
  }, [ticker, scope, beginRequest]);

  const switchScope = next => { resetRequests(); setScope(next); };
  const contracts = Array.isArray(chain?.contracts) ? chain.contracts : [];
  const spot = typeof chain?.spot === "number" ? chain.spot : null;
  const series = admittedExposure(chain, ticker, expiry);
  const selectedRows = selection
    ? contracts.filter(c => Number(c.strike) === Number(selection.strike)) : [];
  const selectedRow = selectedRows.find(c => c.gex != null && Number.isFinite(Number(c.gex)))
    || selectedRows[0] || null;

  const copyTriadContext = async () => {
    const payload = {
      kind: "triad-context", version: 1, ticker, scope, expiry,
      selection, spot,
      chain_source: chain?.data_source || null,
      chain_fetched_at: chain?.fetched_at || null,
      exposure_series_version: series?.series_version || null,
      exposure_coverage: series?.coverage || null,
      exposure_source_coverage: series?.source_coverage || null,
      note: "research-only frozen scope; not an execution permission",
    };
    try {
      await navigator.clipboard.writeText(JSON.stringify(payload));
      setCopyStatus("Context copied.");
    } catch (e) {
      setCopyStatus("Copy failed: clipboard unavailable.");
    }
  };

  return <section aria-label="Triad same-day wall desk">
    <div className="context-mini">
      <strong>{ticker}</strong>
      <span className="mono">{spot != null ? `Spot ${spot}` : "Spot unknown"}</span>
      <button type="button" aria-pressed={scope === "0dte"} onClick={() => switchScope("0dte")}>0DTE</button>
      <button type="button" aria-pressed={scope === "next"} onClick={() => switchScope("next")}>Next listed</button>
      <small>{expiry ? `${expiry} · same observation` : "no expiry selected"}</small>
    </div>
    {expiriesNote && !expiry && <div className="panel empty" role="status">
      <h2>{ticker}: same-day chain not verified</h2>
      <p>{expiriesNote}</p>
      {scope === "0dte" && <button type="button" onClick={() => switchScope("next")}>Review next listed expiry</button>}
      <p>Next listed remains a dated, separate scope.</p>
    </div>}
    {chainError && <p role="alert">Triad scope unavailable · {chainError}</p>}
    {expiry && !chainError && <>
      <div className="panel exposure"><div className="panelhead">
        <strong>Exposure by strike</strong>
        <div className="chart-legend"><span>Measured over</span><span>Partial hatched</span><span>Unknown gray</span></div>
      </div>
        {series ? <TriadExposure series={series} spot={spot}
          selectedStrike={selection ? Number(selection.strike) : null}
          onSelect={strike => setSelection({ strike: String(strike), expiry })} />
          : <p role="status">Admitted exposure unavailable for this chain snapshot. Contract rows remain available for review.</p>}
        <div className="chart-caption">Same strike rail · {expiry} · server-admitted exposure; unknown rows are not neutral.
          {series && <> Receipt {series.fetched_at || 'unknown'} · observation {series.event_time || 'unknown'}.</>}
          {series?.source_coverage?.skipped?.length > 0 && <span> Source coverage includes skipped expiries; displayed rows do not prove complete listing coverage.</span>}
        </div>
      </div>
      <TriadChainTable rows={contracts} expiry={expiry}
        selectedStrike={selection ? Number(selection.strike) : null}
        onReview={sel => setSelection(sel)} />
      <aside aria-label="Triad wall review">
        <h3>Wall read</h3>
        <p>{selection
          ? `Selected ${selection.strike} · ${selection.expiry} · ${ticker}. A selection is a zone focus, not a classified structural wall.`
          : "Select a strike to focus review; nothing is selected."}</p>
        <h3>Selected contract</h3>
        {selectedRow ? <p>
          {(selectedRow.osi || `${selectedRow.type || "option"} ${selectedRow.strike}`)} · {selectedRow.expiry || expiry} ·&nbsp;
          bid {selectedRow.bid ?? "unknown"} / ask {selectedRow.ask ?? "unknown"} ·&nbsp;
          exposure {selectedRow.gex != null && Number.isFinite(Number(selectedRow.gex))
            ? `${selectedRow.gex} (${selectedRow.gex_basis || "basis unknown"})` : "unknown (not zero)"}
        </p> : <p>No contract selected — or the selected strike carries no listed row.</p>}
        <h3>Entry and protection</h3>
        <p>Entry only after your price confirmation, in whole contracts at broker increments. Exact supported contract plus commissioned policy required; this desk grants neither.</p>
        <h3>Lodestar context</h3>
        <button type="button" onClick={copyTriadContext}>Copy Triad context</button>
        {copyStatus && <p role="status">{copyStatus}</p>}
        <h3>Handoff trace</h3>
        <p>{selection
          ? `Wall context attached · ${ticker} · ${selection.strike} · ${selection.expiry} · chain ${chain?.fetched_at || "time unknown"}`
          : "No selection attached."} Execution owner: unselected — choosing an owner labels a future draft only and never authorizes entry.</p>
      </aside>
    </>}
  </section>;
}

import React, { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import axios from "axios";
import { API } from "../../config/api";
import { buildTickerUniverse, normalizeTicker, searchUniverse, UNIVERSE_MAX_PAGES, UNIVERSE_PAGE_LIMIT } from "./tickerUniverse";
import "./TickerPicker.css";
import useMarketCoverage from "./useMarketCoverage";

export const FAVORITES_KEY = "floww-symbol-favorites-v1";
const FAVORITES_CHANGED = "floww-symbol-favorites-changed";
const PAGE_SIZE = 30;
const validSymbol = value => typeof value === "string" && /^\^?[A-Z][A-Z0-9.-]{0,11}$/.test(value);
function readFavorites(onError) {
  try {
    const saved = JSON.parse(localStorage.getItem(FAVORITES_KEY));
    return Array.isArray(saved) ? [...new Set(saved.filter(validSymbol))] : [];
  } catch { onError?.(); return []; }
}

/** Selection and favorites only: this component never changes scanner scope. */
export default function TickerPicker({ value = "SPY", onChange, tickers = null, status = "unknown", onRetry, ariaLabel = "Search stocks", className = "" }) {
  const universe = useMemo(() => buildTickerUniverse(tickers).filter(validSymbol), [tickers]);
  const active = normalizeTicker(value);
  const globalPicker = className.split(/\s+/).includes("floww-header-symbol-picker");
  const coverage = useMarketCoverage(globalPicker);
  const [category, setCategory] = useState("all"), [sector, setSector] = useState("");
  const [catalog, setCatalog] = useState(null), [catalogState, setCatalogState] = useState("idle"), [catalogAttempt, setCatalogAttempt] = useState(0);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [index, setIndex] = useState(-1);
  const [page, setPage] = useState(0);
  const [favorites, setFavorites] = useState(readFavorites);
  const [message, setMessage] = useState("");
  const [checking, setChecking] = useState(false);
  const [position, setPosition] = useState({ left: 8, top: 40, width: 300, maxHeight: 420 });
  const control = useRef(null), popup = useRef(null), input = useRef(null);
  const request = useRef(null), epoch = useRef(0);
  const listId = useId();
  const noteId = useId();
  const filteredCatalog = globalPicker && category !== "favorites";
  const catalogKey = JSON.stringify([category,sector,normalizeTicker(query),page]);
  const currentCatalog = catalog?.key === catalogKey ? catalog.data : null;
  const localMatches = useMemo(() => {
    const available = category === "favorites" ? favorites : universe;
    return query.trim() ? searchUniverse(available, normalizeTicker(query), available.length).matches : available;
  }, [universe, query, category, favorites]);
  const matches = filteredCatalog ? (currentCatalog?.instruments || []).map(row => row.symbol) : localMatches;
  const matchCount = filteredCatalog ? currentCatalog?.matches || 0 : matches.length;
  const totalPages = Math.max(1, Math.ceil(matchCount / PAGE_SIZE));
  const safePage = filteredCatalog ? page : Math.min(page, totalPages - 1);
  const shown = filteredCatalog ? matches : matches.slice(safePage * PAGE_SIZE, (safePage + 1) * PAGE_SIZE);
  const highlighted = index >= safePage * PAGE_SIZE && index < (safePage + 1) * PAGE_SIZE && index < matchCount ? index : -1;
  const sectors = useMemo(() => Array.isArray(coverage.data?.directory.sectors) ? coverage.data.directory.sectors.filter(value => typeof value === "string" && value.trim()) : [], [coverage.data]);
  useEffect(() => {
    if (coverage.status === "ready" && sector && !sectors.includes(sector)) {setSector("");setPage(0);setIndex(-1);}
  }, [coverage.status,sectors,sector]);
  useEffect(() => {
    if (filteredCatalog && currentCatalog && page >= totalPages) {setPage(totalPages-1);setIndex(-1);}
  }, [filteredCatalog,currentCatalog,page,totalPages]);
  useEffect(() => {
    if (!open || !filteredCatalog) return undefined;
    const controller = new AbortController();let active = true;setCatalog(null);setCatalogState("loading");
    const timer = setTimeout(async () => {
      try {
        const {data} = await axios.get(API+"/market/catalog", {params:{page:page+1,limit:PAGE_SIZE,q:normalizeTicker(query),options_only:category==="options",...(sector?{sector}:{})},signal:controller.signal,timeout:15000});
        if (!active) return;
        if (!Array.isArray(data?.instruments) || data.instruments.length > PAGE_SIZE || !Number.isSafeInteger(data.matches) || data.matches < data.instruments.length || data.instruments.some(row => !validSymbol(row?.symbol) || normalizeTicker(query) && !row.symbol.includes(normalizeTicker(query)) || category === "options" && row.options !== true || sector && row.sector !== sector)) throw Error("Invalid filtered list");
        if (data.complete_provider_catalog === false && !data.instruments.length) throw Error("Provider list unavailable");
        if (data.page != null && data.page !== page+1 || data.limit != null && data.limit !== PAGE_SIZE) throw Error("Wrong catalogue page");
        setCatalog({key:catalogKey,data});setCatalogState("ready");
      } catch { if (active && !controller.signal.aborted) setCatalogState("error"); }
    }, 150);
    return () => {active=false;clearTimeout(timer);controller.abort();};
  }, [open,filteredCatalog,category,sector,query,page,catalogKey,catalogAttempt]);
  const stopLookup = useCallback(() => { epoch.current++; request.current?.abort(); request.current = null; setChecking(false); }, []);
  const close = useCallback(() => { stopLookup(); setOpen(false); setIndex(-1); }, [stopLookup]);

  useEffect(() => {
    const refresh = () => setFavorites(readFavorites(() => setMessage("Saved favorites could not be read. Check browser storage and try again.")));
    refresh();
    const storage = event => { if (event.key === FAVORITES_KEY || event.key === null) refresh(); };
    window.addEventListener("storage", storage);
    window.addEventListener(FAVORITES_CHANGED, refresh);
    return () => { epoch.current++; request.current?.abort(); window.removeEventListener("storage", storage); window.removeEventListener(FAVORITES_CHANGED, refresh); };
  }, []);
  useEffect(() => { stopLookup(); }, [active, universe, stopLookup]);
  useEffect(() => {
    if (!open) return undefined;
    const outside = event => { if (!control.current?.contains(event.target) && !popup.current?.contains(event.target)) close(); };
    document.addEventListener("mousedown", outside); document.addEventListener("focusin", outside);
    return () => { document.removeEventListener("mousedown", outside); document.removeEventListener("focusin", outside); };
  }, [open, close]);
  useLayoutEffect(() => {
    if (!open) return undefined;
    const place = () => {
      const rect = control.current?.getBoundingClientRect();
      if (!rect) return;
      const width = Math.min(340, window.innerWidth - 16);
      const below = window.innerHeight - rect.bottom - 12;
      const above = rect.top - 12;
      const upwards = below < 240 && above > below;
      const maxHeight = Math.max(100, Math.min(420, upwards ? above : below));
      setPosition({ width, left: Math.max(8, Math.min(rect.left, window.innerWidth - width - 8)), top: upwards ? undefined : rect.bottom + 4, bottom: upwards ? window.innerHeight - rect.top + 4 : undefined, maxHeight });
    };
    place(); window.addEventListener("resize", place); window.addEventListener("scroll", place, true);
    return () => { window.removeEventListener("resize", place); window.removeEventListener("scroll", place, true); };
  }, [open, message, checking]);
  useEffect(() => {
    if (open && highlighted >= 0) document.getElementById(`${listId}-${highlighted}`)?.scrollIntoView?.({ block: "nearest" });
  }, [open, highlighted, listId]);

  const resolve = async raw => {
    stopLookup();
    const symbol = normalizeTicker(raw);
    if (!validSymbol(symbol)) { setMessage("Choose a valid stock symbol, such as SPY or BRK.B."); return null; }
    if (universe.includes(symbol)) return symbol;
    const current = epoch.current;
    const controller = new AbortController(); request.current = controller;
    const timer = setTimeout(() => controller.abort(), 15000);
    setChecking(true); setMessage("");
    try {
      // Search a provider directory, then require an exact match. A partial
      // local list cannot prove a symbol invalid, and a substring is not identity.
      let complete = false;
      let generation;
      for (let providerPage = 1; providerPage <= UNIVERSE_MAX_PAGES; providerPage++) {
        const { data } = await axios.get(`${API}/market/catalog`, { params: { q: symbol, page: providerPage, limit: UNIVERSE_PAGE_LIMIT }, signal: controller.signal, timeout: 15000 });
        if (epoch.current !== current || controller.signal.aborted) return null;
        if (providerPage > 1 && data?.asof !== generation) break;
        generation = data?.asof;
        if ((data?.instruments || []).some(item => item.symbol === symbol)) return symbol;
        if (data?.has_more !== true) { complete = data?.complete_provider_catalog === true && data?.stale !== true; break; }
      }
      setMessage(complete
        ? "This symbol is not in the provider's available stock list."
        : "This stock could not be confirmed. The provider list is incomplete; try again.");
    } catch {
      if (epoch.current === current) setMessage("This stock could not be confirmed. Check the connection and try again.");
    } finally {
      clearTimeout(timer);
      if (epoch.current === current) { request.current = null; setChecking(false); }
    }
    return null;
  };
  const choose = async raw => {
    setMessage("");
    const local = normalizeTicker(raw);
    if (validSymbol(local) && (universe.includes(local) || currentCatalog?.instruments.some(row => row.symbol === local))) {
      stopLookup(); onChange?.(local); input.current?.focus(); setQuery(""); setOpen(false); setIndex(-1); setPage(0); return;
    }
    const pending = resolve(raw);
    const current = epoch.current;
    const symbol = await pending;
    if (!symbol || epoch.current !== current) return;
    onChange?.(symbol); input.current?.focus(); setQuery(""); setOpen(false); setIndex(-1); setPage(0);
  };
  const toggleFavorite = async () => {
    setMessage("");
    // Removing an old favorite must not require a currently available provider.
    const symbol = favorites.includes(active) || universe.includes(active) ? active : await resolve(active);
    if (!symbol) return;
    let readable = true;
    const saved = readFavorites(() => { readable = false; setMessage("Saved favorites could not be read. Check browser storage and try again."); });
    if (!readable) return;
    const next = saved.includes(symbol) ? saved.filter(item => item !== symbol) : [...saved, symbol];
    try {
      localStorage.setItem(FAVORITES_KEY, JSON.stringify(next)); setFavorites(next);
      window.dispatchEvent(new Event(FAVORITES_CHANGED));
    } catch { setMessage("Favorites could not be saved. Your earlier favorites are unchanged."); }
  };
  const move = direction => {
    setOpen(true);
    if (!matchCount) return;
    const next = index < 0 || index >= matchCount ? direction > 0 ? 0 : matchCount - 1 : Math.max(0, Math.min(matchCount - 1, index + direction));
    setIndex(next); setPage(Math.floor(next / PAGE_SIZE));
  };
  const keyDown = event => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); move(event.key === "ArrowDown" ? 1 : -1); }
    else if (event.key === "Enter") { event.preventDefault(); if(filteredCatalog && (catalogState !== "ready" || !currentCatalog)) return; choose(open && highlighted >= 0 ? shown[highlighted - safePage * PAGE_SIZE] : query); }
    else if (event.key === "Escape" && open) { event.preventDefault(); event.stopPropagation(); close(); }
    else if (event.key === "Tab") close();
  };
  const statusText = status === "loading" ? "Loading the stock list."
    : status === "saved" ? "Using a saved provider list; latest changes are unavailable."
      : status === "incomplete" ? "The local stock list is incomplete. Other names are checked with the provider when selected." : "";

  return <div className={`ticker-picker ${className}`} ref={control}>
    <div className="ticker-picker-control">
      <span className="ticker-picker-current">Selected {active || "none"}</span>
      <input ref={input} type="text" role="combobox" aria-label={ariaLabel} aria-autocomplete="list" aria-haspopup="listbox"
        aria-expanded={open} aria-controls={open ? listId : undefined} aria-activedescendant={open && highlighted >= 0 ? `${listId}-${highlighted}` : undefined}
        aria-describedby={message || checking ? noteId : undefined} value={query} maxLength={40} placeholder="Search stocks"
        onFocus={() => setOpen(true)} onChange={event => { stopLookup(); setQuery(event.target.value); setOpen(true); setIndex(-1); setPage(0); setMessage(""); }} onKeyDown={keyDown} />
      <button type="button" className="ticker-picker-browse" aria-label="Browse stock list" aria-expanded={open} onClick={() => { if (open) close(); else { setOpen(true); input.current?.focus(); } }}>▾</button>
      <button type="button" className="ticker-picker-star" disabled={checking || !validSymbol(active)} aria-label={`${favorites.includes(active) ? "Remove" : "Add"} ${active} ${favorites.includes(active) ? "from" : "to"} favorites`} aria-pressed={favorites.includes(active)} onClick={toggleFavorite}>{favorites.includes(active) ? "★" : "☆"}</button>
    </div>
    {globalPicker && <div className="ticker-picker-feed-counts" data-testid="stock-feed-counts" aria-label="Stock feed counts" title="Checked stocks have received option data in the shown window. Listed names show directory access; they do not prove every stock has recent data.">
      <span>{coverage.data?.directory.available ? coverage.data.directory.total.toLocaleString()+" listed" : "Listed count unknown"}{coverage.data?.directory.stale || coverage.status==="unavailable" && coverage.data ? " (saved list)" : ""}</span>
      <span>{coverage.fresh===null ? "Stock checks unknown" : coverage.fresh.toLocaleString()+" stocks checked"}{coverage.data?.directory.available ? " / "+coverage.data.directory.optionable_total.toLocaleString()+" with options" : ""}{coverage.data?.options.window_seconds ? " in "+Math.round(coverage.data.options.window_seconds/60)+" min" : ""}</span>
      <span>{coverage.status==="unavailable" ? "Feed counts unavailable" : coverage.lastSuccessAge===null ? "Feed last success unknown" : "Feed read "+(coverage.lastSuccessAge<60 ? Math.round(coverage.lastSuccessAge)+"s" : Math.round(coverage.lastSuccessAge/60)+"m")+" ago"}</span>
    </div>}
    {(checking || message) && <p id={noteId} className="ticker-picker-notice" role={message ? "alert" : "status"}>{message || "Checking the provider stock list…"}</p>}
    {open && createPortal(<div ref={popup} className="ticker-picker-popup" style={position} onKeyDown={event => { if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); input.current?.focus(); close(); } }}>
      {statusText && <p className="ticker-picker-status" role="status">{statusText}{onRetry && status !== "loading" && <button type="button" onClick={onRetry}>Retry stock list</button>}</p>}
      {globalPicker && <div className="ticker-picker-filters">
        <label>Category <select aria-label="Stock category" value={category} onChange={event => {stopLookup();setCategory(event.target.value);setSector("");setPage(0);setIndex(-1);}}><option value="all">All listed</option><option value="options">Options enabled</option><option value="favorites">Favorites</option></select></label>
        <label>Sector <select aria-label="Stock sector" disabled={!sectors.length || category==="favorites"} value={sector} onChange={event => {stopLookup();setSector(event.target.value);setPage(0);setIndex(-1);}}><option value="">{sectors.length ? "All supplied sectors" : "Sector details unavailable"}</option>{sectors.map(value => <option key={value} value={value}>{value}</option>)}</select></label>
        {sectors.length > 0 && <small>{coverage.data?.directory.sector_classified?.toLocaleString()} names have supplied sector details; others remain unclassified.</small>}
      </div>}
      {!query.trim() && favorites.length > 0 && <div className="ticker-picker-favorites" aria-label="Favorite stocks"><span>Favorites</span>{favorites.map(symbol => <button type="button" key={symbol} onClick={() => choose(symbol)}>{symbol}</button>)}</div>}
      <div className="ticker-picker-result-count">{(filteredCatalog && !currentCatalog ? "Unknown" : matchCount.toLocaleString())} {query.trim() ? "matches" : filteredCatalog ? "listed stocks" : "loaded stocks"} · Page {safePage + 1} of {filteredCatalog && !currentCatalog ? "unknown" : totalPages}</div>
      <div id={listId} role="listbox" aria-label="Stock suggestions" className="ticker-picker-list">
        {shown.map((symbol, offset) => { const optionIndex = safePage * PAGE_SIZE + offset; return <div id={`${listId}-${optionIndex}`} key={symbol} role="option" aria-label={symbol} aria-selected={highlighted === optionIndex} className={`ticker-picker-option${highlighted === optionIndex ? " highlighted" : ""}`} onMouseDown={event => event.preventDefault()} onClick={() => choose(symbol)}><span>{symbol}</span>{symbol === active && <small>Selected</small>}{favorites.includes(symbol) && <span aria-label="Favorite">★</span>}</div>; })}
      </div>
      {filteredCatalog && catalogState === "loading" && <p className="ticker-picker-status" role="status">Loading this stock group...</p>}
      {filteredCatalog && catalogState === "error" && <p className="ticker-picker-status" role="alert">This stock group could not be loaded. Matches are unavailable. <button type="button" onClick={()=>setCatalogAttempt(value=>value+1)}>Retry stock group</button></p>}
      {filteredCatalog && currentCatalog?.complete_provider_catalog === false && <p className="ticker-picker-status" role="status">The provider stock list is incomplete; other names may be missing.</p>}
      {filteredCatalog && currentCatalog?.stale && <p className="ticker-picker-status">This group uses a saved provider list.</p>}
      {!shown.length && (!filteredCatalog || catalogState === "ready") && <p className="ticker-picker-status">{category==="favorites" ? "No matching favorites." : "No loaded matches. Press Enter or check the provider to find this stock."}</p>}
      {query.trim() && <button type="button" className="ticker-picker-lookup" disabled={checking} onClick={() => choose(query)}>{checking ? "Checking…" : "Choose this stock"}</button>}
      {totalPages > 1 && <div className="ticker-picker-pages"><button type="button" disabled={safePage === 0 || filteredCatalog && catalogState === "loading"} onClick={() => { setPage(safePage - 1); setIndex((safePage - 1) * PAGE_SIZE); }}>Previous</button><button type="button" disabled={safePage >= totalPages - 1 || filteredCatalog && (!currentCatalog || catalogState !== "ready")} onClick={() => { setPage(safePage + 1); setIndex((safePage + 1) * PAGE_SIZE); }}>Next</button></div>}
    </div>, document.body)}
  </div>;
}

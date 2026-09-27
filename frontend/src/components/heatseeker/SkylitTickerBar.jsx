import React, { memo, useEffect, useMemo, useRef, useState } from "react";
import {
  RENDER_CAP,
  SUGGEST_CAP,
  buildTickerUniverse,
  normalizeTicker,
  searchUniverse,
} from "./tickerUniverse";

/**
 * SkylitTickerBar — Top ticker tape with quick-select buttons + search.
 * Receives `tickers` from App.js (object { trinity, default, popular }).
 *
 * T1 contract (2026-09-07): buttons, count, arrows and search share one
 * case-normalized deduped universe. Rendered buttons are capped at
 * RENDER_CAP for DOM perf with an honest "showing X of N" label; search
 * filters the FULL universe before capping suggestions, so every intended
 * ticker stays reachable. Free-text submit (open universe) is preserved.
 * The active ticker is always rendered, even beyond the cap, and scrolled
 * into view on change.
 */
const DEFAULT_TICKERS = [
  "SPY", "QQQ", "IWM", "DIA", "AAPL", "NVDA", "TSLA", "META",
  "AMZN", "MSFT", "AMD", "GOOGL", "RIVN", "RBLX", "HIMS",
  "IREN", "MU", "NOW", "OSCR", "PATH", "UPS", "ZETA", "SPXW",
];

export const TICKER_SETS = {
  default: DEFAULT_TICKERS,
  popular: ["SPY", "QQQ", "IWM", "DIA", "AAPL", "NVDA", "TSLA", "META", "AMZN", "MSFT"],
  tech: ["AAPL", "NVDA", "MSFT", "GOOGL", "META", "AMD", "TSLA"],
  etfs: ["SPY", "QQQ", "IWM", "DIA", "VTI", "VOO", "ARKK", "XLF", "XLE", "XLV"],
};

function SkylitTickerBar({
  activeTicker = "SPY",
  onTickerChange,
  tickers = null,
  allCount = 703,
}) {
  const universe = useMemo(() => {
    const u = buildTickerUniverse(tickers);
    return u.length > 0 ? u : [...DEFAULT_TICKERS];
  }, [tickers]);

  const active = normalizeTicker(activeTicker);
  // Paged A-Z window: 500-button slices of the full universe with prev/next
  // controls, so every symbol is reachable by scrolling. The page follows the
  // active ticker (keyboard/control-bar steps through the full universe).
  const totalPages = Math.max(1, Math.ceil(universe.length / RENDER_CAP));
  const pageFor = (t) => Math.max(0, Math.floor(universe.indexOf(t) / RENDER_CAP));
  const [page, setPage] = useState(() => (active ? pageFor(active) : 0));
  useEffect(() => {
    if (active && universe.includes(active)) {
      const p = Math.min(pageFor(active), totalPages - 1);
      setPage((prev) => (prev === p ? prev : p));
    }
  }, [active, universe, totalPages]);
  const safePage = Math.min(page, totalPages - 1);
  // Rendered window: the current page slice plus the active ticker when it
  // falls outside (transition safety), so selection and buttons never disagree.
  const visible = useMemo(() => {
    const win = universe.slice(safePage * RENDER_CAP, safePage * RENDER_CAP + RENDER_CAP);
    if (active && universe.includes(active) && !win.includes(active)) {
      win.push(active);
    }
    return win;
  }, [universe, active, safePage]);

  const [query, setQuery] = useState("");
  const { matches: suggestions, total: suggestTotal } = useMemo(
    () => searchUniverse(universe, query, SUGGEST_CAP),
    [universe, query]
  );

  // Reveal the active button when selection changes (O-3: keyboard selection
  // and the visible scroll surface agree, including items past the cap).
  const activeRef = useRef(null);
  useEffect(() => {
    if (activeRef.current && typeof activeRef.current.scrollIntoView === "function") {
      try {
        activeRef.current.scrollIntoView({ block: "nearest", inline: "nearest" });
      } catch (_) { /* jsdom / old browsers: visibility is asserted by render */ }
    }
  }, [active]);

  const submitQuery = (raw) => {
    const t = normalizeTicker(raw !== undefined ? raw : query);
    if (t && onTickerChange) {
      onTickerChange(t);
      setQuery("");
    }
  };

  return (
    <div className="skylit-ticker-bar">
      <div className="skylit-ticker-scroll">
        <div className="skylit-ticker-inner">
          <span className="skylit-ticker-count" data-testid="skylit-ticker-count">
            {universe.length > RENDER_CAP
              ? `showing ${visible.length} of ${universe.length} · page ${safePage + 1}/${totalPages}`
              : `${universe.length} tickers`}
          </span>
          {totalPages > 1 && (
            <>
              <button
                className="skylit-ticker-btn"
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={safePage <= 0}
                title="Previous 500"
                data-testid="skylit-ticker-page-prev"
              >
                ‹
              </button>
              <button
                className="skylit-ticker-btn"
                onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                disabled={safePage >= totalPages - 1}
                title="Next 500"
                data-testid="skylit-ticker-page-next"
              >
                ›
              </button>
            </>
          )}
          <span className="skylit-ticker-sep">|</span>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") submitQuery(); }}
            placeholder="Search any ticker…"
            aria-label="Search any ticker"
            data-testid="skylit-ticker-search"
            className="skylit-ticker-search"
          />
          <button
            className="skylit-ticker-btn"
            onClick={() => submitQuery()}
            title="Load ticker"
            data-testid="skylit-ticker-go"
          >
            Go
          </button>
          {suggestions.length > 0 && (
            <span className="skylit-ticker-more" data-testid="skylit-ticker-suggest-count">
              {suggestTotal} match{suggestTotal === 1 ? "" : "es"}
            </span>
          )}
          {suggestions.map((t) => (
            <button
              key={`s-${t}`}
              className="skylit-ticker-btn"
              data-testid={`skylit-ticker-suggest-${t}`}
              onClick={() => submitQuery(t)}
              title={`Load ${t}`}
            >
              {t}
            </button>
          ))}
          <span className="skylit-ticker-sep">|</span>
          {visible.map((t) => (
            <button
              key={t}
              ref={t === active ? activeRef : undefined}
              data-testid={`skylit-ticker-btn-${t}`}
              className={`skylit-ticker-btn${t === active ? " active" : ""}`}
              onClick={() => onTickerChange && onTickerChange(t)}
            >
              {t}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

export default memo(SkylitTickerBar);

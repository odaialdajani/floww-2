import React, { memo, useState } from "react";

/**
 * SkylitTickerBar — Top ticker tape with quick-select buttons + free-text
 * search (2026-09-03: open universe — any symbol, not just the tape list).
 * Matches Zenith reference: scrollable row of ticker buttons
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
  const tickerList = tickers?.popular || tickers?.default || DEFAULT_TICKERS;
  const [query, setQuery] = useState("");

  const submitQuery = () => {
    const t = query.trim().toUpperCase().replace(/^\$/, "");
    if (t && onTickerChange) {
      onTickerChange(t);
      setQuery("");
    }
  };

  return (
    <div className="skylit-ticker-bar">
      <div className="skylit-ticker-scroll">
        <div className="skylit-ticker-inner">
          <span className="skylit-ticker-count">All Tickers {allCount}</span>
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
            onClick={submitQuery}
            title="Load ticker"
            data-testid="skylit-ticker-go"
          >
            Go
          </button>
          <span className="skylit-ticker-sep">|</span>
          {tickerList.map((t) => (
            <button
              key={t}
              className={`skylit-ticker-btn${t === activeTicker ? " active" : ""}`}
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

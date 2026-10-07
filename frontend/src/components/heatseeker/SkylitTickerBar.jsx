import React, {memo, useMemo} from "react";
import TickerPicker from "./TickerPicker";
import {buildTickerUniverse} from "./tickerUniverse";

const DEFAULT_TICKERS = ["SPY", "QQQ", "IWM", "DIA", "AAPL", "NVDA", "TSLA", "META", "AMZN", "MSFT", "AMD", "GOOGL", "RIVN", "RBLX", "HIMS", "IREN", "MU", "NOW", "OSCR", "PATH", "UPS", "ZETA", "SPXW"];
export const TICKER_SETS = {
 default: DEFAULT_TICKERS,
 popular: ["SPY", "QQQ", "IWM", "DIA", "AAPL", "NVDA", "TSLA", "META", "AMZN", "MSFT"],
 tech: ["AAPL", "NVDA", "MSFT", "GOOGL", "META", "AMD", "TSLA"],
 etfs: ["SPY", "QQQ", "IWM", "DIA", "VTI", "VOO", "ARKK", "XLF", "XLE", "XLV"],
};

/** Compact browsing and full-list search; favorites never change data coverage. */
function SkylitTickerBar({activeTicker="SPY", onTickerChange, tickers=null, directoryStatus="unknown", onRetryDirectory}) {
 const universe=useMemo(()=>{const list=buildTickerUniverse(tickers);return list.length?list:[...DEFAULT_TICKERS];},[tickers]);
 return <div className="ticker-picker-bar">
  <TickerPicker value={activeTicker} onChange={onTickerChange} tickers={universe} status={directoryStatus} onRetry={onRetryDirectory} ariaLabel="Search any ticker"/>
  <span className="ticker-picker-bar-count" data-testid="skylit-ticker-count">{universe.length.toLocaleString()} loaded tickers</span>
 </div>;
}
export default memo(SkylitTickerBar);

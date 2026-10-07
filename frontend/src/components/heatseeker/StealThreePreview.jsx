import React, { memo, useState } from "react";
import DualGEXBadge from "./DualGEXBadge";
import IVMidBadge from "./IVMidBadge";
import WheelIncomeScreenerPanel from "./WheelIncomeScreenerPanel";
import TickerPicker from "./TickerPicker";
import "./StealThreePreview.css";
import NavigationScreenContext from "../../agent/NavigationScreenContext";

const STUDIES = [["income", "Options income"], ["exposure", "Exposure comparison"], ["volatility", "Volatility comparison"]];

function StealThreePreview({ defaultTicker = "SPY", ticker: sharedTicker, onTickerChange }) {
  const [localTicker, setLocalTicker] = useState(defaultTicker);
  const ticker = sharedTicker ?? localTicker;
  const chooseTicker = next => {
    if (sharedTicker == null) setLocalTicker(next);
    onTickerChange?.(next);
  };
  const [study, setStudy] = useState("income");
  const [visited, setVisited] = useState(() => new Set(["income"]));
  const chooseStudy = event => {
    const next = event.target.value;
    if (!STUDIES.some(([id]) => id === next)) return;
    setStudy(next);
    setVisited(previous => previous.has(next) ? previous : new Set([...previous,next]));
  };
  const family = (id,children) => visited.has(id)
    ? <section className="extra-study-family" data-extra-study={id} hidden={study !== id}>{children}</section> : null;
  return <div className="extra-studies" data-testid="steal-three-preview">
    <NavigationScreenContext page="steal-three" ticker={ticker} study={STUDIES.find(([id]) => id === study)?.[1]} />
    <div className="extra-study-toolbar">
      <label>Study <select aria-label="Study" value={study} onChange={chooseStudy}>
        {STUDIES.map(([id,label]) => <option key={id} value={id}>{label}</option>)}
      </select></label>
      {sharedTicker == null && <TickerPicker value={ticker} onChange={chooseTicker} ariaLabel="Extra study stock" />}
      <span>{ticker} · Each study keeps its own source and reading time.</span>
    </div>
    {family("income", <WheelIncomeScreenerPanel ticker={ticker} />)}
    {family("exposure", <DualGEXBadge ticker={ticker} />)}
    {family("volatility", <IVMidBadge ticker={ticker} width={6} />)}
  </div>;
}
export default memo(StealThreePreview);

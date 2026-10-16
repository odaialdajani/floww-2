import React, {useId, useRef, useState} from "react";
import "./ReviewInspector.css";

const SECTIONS = [["wall", "Wall"], ["contract", "Contract"], ["flow", "Flow"], ["publicAgent", "Public agent"]];

// Presentation only: keep the existing fact, exact-contract and single-agent
// consumers mounted. Changing steps neither refetches nor invokes research.
function InspectorSections({wall, contract, flow, publicAgent, initialTab = "wall"}) {
  const id = useId();
  const tabs = useRef([]);
  const [active, setActive] = useState(SECTIONS.some(([key]) => key === initialTab) ? initialTab : "wall");
  const panels = {wall, contract, flow, publicAgent};
  const navigate = (event, index) => {
    let next;
    if (event.key === "ArrowRight") next = (index + 1) % SECTIONS.length;
    else if (event.key === "ArrowLeft") next = (index + SECTIONS.length - 1) % SECTIONS.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = SECTIONS.length - 1;
    else return;
    event.preventDefault();
    event.stopPropagation();
    setActive(SECTIONS[next][0]);
    tabs.current[next]?.focus();
  };
  return <div className="review-inspector">
    <div className="review-inspector-tabs" role="tablist" aria-label="Inspector sections">
      {SECTIONS.map(([key, label], index) => <button key={key} ref={el => { tabs.current[index] = el; }}
        type="button" role="tab" id={`${id}-${key}-tab`} aria-controls={`${id}-${key}-panel`}
        aria-selected={active === key} tabIndex={active === key ? 0 : -1}
        onClick={() => setActive(key)} onKeyDown={event => navigate(event, index)}>{label}</button>)}
    </div>
    {SECTIONS.map(([key]) => <section key={key} role="tabpanel" className="review-inspector-panel"
      id={`${id}-${key}-panel`} aria-labelledby={`${id}-${key}-tab`} hidden={active !== key} tabIndex={0}>
      {panels[key]}
    </section>)}
  </div>;
}

export default function ReviewInspector({selectionKey, ...props}) {
  return <InspectorSections key={selectionKey} {...props}/>;
}

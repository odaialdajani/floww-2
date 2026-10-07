/** One visible study family; visited panels retain their controls and readings. */

import React, { useMemo, useState, useEffect, useRef, memo } from "react";
import "./HeatseekerDashboard.css";
import NavigationScreenContext from "../../agent/NavigationScreenContext";
import CharmDecayPanel from "./CharmDecayPanel";
import BriefingStrip from "./BriefingStrip";

// ── Lazy-loaded below-the-fold rows ─────────────────────────────────

function LazyRow({ children, rootMargin = "200px" }) {
  const ref = useRef(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) setVisible(true); },
      { rootMargin }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [rootMargin]);
  return <div ref={ref}>{visible ? children : <div className="h-12" />}</div>;
}

// ── Stale Data Badge ─────────────────────────────────────────────────

export const StaleDataBadge = memo(function StaleDataBadge({ dataAge, dataFallback }) {
  if (!dataAge && !dataFallback) return null;
  const ageMin = dataAge != null ? Math.round(dataAge / 60000) : null;
  const show = dataFallback || (ageMin != null && ageMin >= 15);
  if (!show) return null;
  return (
    <span className="inline-flex items-center gap-1 text-[9px] uppercase tracking-widest font-bold px-2 py-0.5 rounded"
      style={{ background: "rgba(251,191,36,0.12)", border: "1px solid rgba(251,191,36,0.3)", color: "#fbbf24" }}>
      <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
      Stale {ageMin != null ? `${ageMin}m` : ""}
    </span>
  );
});

// ── Offline Banner ───────────────────────────────────────────────────

export const OfflineBanner = memo(function OfflineBanner({ isOffline }) {
  if (!isOffline) return null;
  return (
    <div className="flex items-center gap-2 text-[10px] uppercase tracking-widest font-bold px-3 py-1.5 mb-2 rounded-lg"
      style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", color: "#f87171" }}>
      <span className="w-2 h-2 rounded-full bg-red-500" />
      Offline Mode — showing cached data
    </div>
  );
});

// ── Gamma Regime Banner ──────────────────────────────────────────────

function GammaRegimeBanner({ data }) {
  if (!data) return null;
  const regime = data?.regime?.gex_regime || data?.gex_regime;
  if (!regime) return null;
  const isPositive = regime === "positive";
  const isNegative = regime === "negative";
  const color = isPositive ? "emerald" : isNegative ? "rose" : "amber";
  const label = isPositive ? "🟢 Positive Gamma" : isNegative ? "🔴 Negative Gamma" : "🟡 Neutral Gamma";
  const desc = isPositive
    ? "Dealers dampen volatility. Mean-reversion plays favored."
    : isNegative
    ? "Dealers amplify moves. Momentum trades favored."
    : "Mixed signals. Exercise caution.";

  return (
    <div className={`rounded-xl border p-3 mb-4`}
      style={{
        background: isPositive ? "rgba(52,211,153,0.05)" : isNegative ? "rgba(244,63,94,0.05)" : "rgba(251,191,36,0.05)",
        borderColor: isPositive ? "rgba(52,211,153,0.2)" : isNegative ? "rgba(244,63,94,0.2)" : "rgba(251,191,36,0.2)",
      }}>
      <div className="flex items-center justify-between">
        <div>
          <div className={`text-sm font-bold ${isPositive ? "text-emerald-400" : isNegative ? "text-rose-400" : "text-amber-400"}`}>
            {label}
          </div>
          <div className="text-[10px] text-slate-400 mt-0.5">{desc}</div>
        </div>
        {data?.spot && (
          <div className="text-right">
            <div className="text-lg font-bold mono text-slate-200">{data.spot.toFixed(2)}</div>
            <div className="text-[9px] text-slate-500">SPOT</div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Import child panels ───────────────────────────────────────────────

import FlipZonesPanelBase from "./FlipZonesPanel";
import NodeLifecyclePanel from "./NodeLifecyclePanel";
import NodeConfluencePanel from "./NodeConfluencePanel";
import AirPocketsPanel from "./AirPocketsPanel";
import BeachBallIndicator from "./BeachBallIndicator";
import ReverseRugIndicator from "./ReverseRugIndicator";
import RainbowRoadIndicator from "./RainbowRoadIndicator";
import VelocityModeBadge from "./VelocityModeBadge";
import TrinityConfluenceMeter from "./TrinityConfluenceMeter";
// Steal-list top-3 (served by backend/routes/steal_three.py at :8000).
import DualGEXBadge from "./DualGEXBadge";
import IVMidBadge from "./IVMidBadge";
import WheelIncomeScreenerPanel from "./WheelIncomeScreenerPanel";
import MaxPainBadge from "./MaxPainBadge";
// Per-expiry max-pain-drift multi-line chart tile (steal-list #9 rich
// visualization — surfaced via /api/max_pain_drift/{ticker}/per_expiry_history).
import MaxPainPerExpiryDriftTile from "./MaxPainPerExpiryDriftTile";
// Historical steal-list signals (steal-list #6/#9/#10/#20 — backend
// services landed in routes/steal_three.py).
import ConfluenceVelocityRow from "./ConfluenceVelocityRow";
// Steal-list #10 + #8 + news — Row 4 mount ("Expected Moves / Trade Ideas").
import StrikeConeBadge from "./StrikeConeBadge";
import OpportunityBadge from "./OpportunityBadge";
// Catalysts/news pulse (steal-list news feed) — Row 4 3rd-column tile,
// fetches /api/news/{ticker}/history?days=14 on a 5 min poll.
import NewsBadge from "./NewsBadge";
// Steal-list #4 RND (Breeden-Litzenberger PDF/CDF) — Row 4b full-width
// beneath the 3-col Row 4 grid per the panel's own docstring spec.
// Fetches GET /api/rnd/{ticker}?expiry_index=N and renders PDF + CDF
// SVG + tail-prob chips.
import RndDensityPanel from "./RndDensityPanel";
import RollingFloorsCeilingsPanelBase from "./RollingFloorsCeilingsPanel";
import NodeClassificationPanelBase from "./NodeClassificationPanel";
import StackedNodesPanelBase from "./StackedNodesPanel";
import TugOfWarZonesPanelBase from "./TugOfWarZonesPanel";
import ErrorBoundary from "../ErrorBoundary";

const VannaChart = React.lazy(() => import("../VannaChart"));
const CharmChart = React.lazy(() => import("../CharmChart"));

export const FlipZonesPanel = memo(FlipZonesPanelBase);
export const RollingFloorsCeilingsPanel = memo(RollingFloorsCeilingsPanelBase);
export const NodeClassificationPanel = memo(NodeClassificationPanelBase);
export const StackedNodesPanel = memo(StackedNodesPanelBase);
export const TugOfWarZonesPanel = memo(TugOfWarZonesPanelBase);

// ── Hero Section ──────────────────────────────────────────────────────

// Exported for the data-contract test in HeroSection.contract.test.jsx.
export function HeroSection({ ticker, spot, data, dataAge, dataFallback }) {
  // Field paths below match the actual /api/data/{ticker} response. The
  // previous paths (data.nodes.find(n => n.type === "king"),
  // data.net_gex_total, data.flip_zones[0].price) are not emitted by any
  // route, so all three tiles rendered the em-dash placeholder while the
  // rest of the page showed live numbers. See the contract test for the
  // captured response shape.
  const kongNode = data?.nodes?.king;
  const netGex = data?.metrics?.gex_net_v1;
  const flipPoint = data?.gamma_flip?.gamma_flip;

  return (
    <div className="study-summary" data-testid="study-summary">
      <div className="study-summary-heading">
        <div className="flex items-center gap-2">

          <span className="text-xs font-bold text-slate-200 uppercase tracking-wider">{ticker}</span>
          <span className="study-summary-status">{data ? dataFallback ? "Earlier reading" : "Reading shown" : "No reading"}</span>
        </div>
        <StaleDataBadge dataAge={dataAge} dataFallback={dataFallback} />
      </div>

      <div className="study-summary-values">
        <div className="study-summary-value">
          <div className="text-[9px] text-slate-500 uppercase tracking-wider mb-0.5">Spot</div>
          <div className="text-xl font-bold mono text-slate-100">{spot ? spot.toFixed(2) : "—"}</div>
        </div>
        <div className="study-summary-value">
          <div className="text-[9px] text-slate-500 uppercase tracking-wider mb-0.5">King Node</div>
          <div className="text-xl font-bold mono text-amber-400">{kongNode ? `$${Number(kongNode.strike || kongNode).toFixed(0)}` : "—"}</div>
        </div>
        <div className="study-summary-value">
          <div className="text-[9px] text-slate-500 uppercase tracking-wider mb-0.5">Net GEX</div>
          <div className={`text-xl font-bold mono ${netGex > 0 ? "text-emerald-400" : "text-rose-400"}`}>
            {netGex != null ? `${netGex >= 0 ? "+" : ""}${(netGex / 1e6).toFixed(1)}M` : "—"}
          </div>
        </div>
        <div className="study-summary-value">
          <div className="text-[9px] text-slate-500 uppercase tracking-wider mb-0.5">Flip Point</div>
          <div className="text-xl font-bold mono text-purple-400">{flipPoint ? `$${flipPoint.toFixed(0)}` : "—"}</div>
        </div>
      </div>
    </div>
  );
}

// ── Main Dashboard ────────────────────────────────────────────────────

const STUDIES = [
  ["levels", "Price levels"], ["patterns", "Patterns"], ["income", "Options income"],
  ["history", "Changes over time"], ["moves", "Expected moves"],
  ["structure", "More levels"], ["exposure", "Option exposure"], ["briefing", "Market brief"],
];

function StudyFamily({ id, active, visited, children }) {
  if (!visited.has(id)) return null;
  // Once visited, keep the actual panel mounted. Its controls and original
  // reading clocks survive study changes; hidden families take no page space.
  return <section className="study-family" data-study-family={id} hidden={active !== id}>{children}</section>;
}

export default function HeatseekerDashboard({
  ticker = "SPY", spot = null, data = null, isOffline = false,
  dataAge = null, dataFallback = false, extraStudies = {},
}) {
  const normalizedTicker = useMemo(() => String(ticker).toUpperCase(), [ticker]);
  const [study, setStudy] = useState("levels");
  const [visited, setVisited] = useState(() => new Set(["levels"]));
  const chooseStudy = event => {
    const next = event.target.value;
    if (!STUDIES.some(([id]) => id === next)) return;
    setStudy(next);
    setVisited(previous => previous.has(next) ? previous : new Set([...previous, next]));
  };
  const family = (id, children) => <StudyFamily id={id} active={study} visited={visited}>
    {children}
    {extraStudies?.[id] != null && extraStudies[id] !== false && <div className="study-extras">{extraStudies[id]}</div>}
  </StudyFamily>;
  return <div className="study-workspace" data-testid="heatseeker-dashboard">
    <NavigationScreenContext page="heatseeker" ticker={normalizedTicker} study={STUDIES.find(([id]) => id === study)?.[1]} />
    <div className="study-toolbar">
      <label>Study <select aria-label="Study" value={study} onChange={chooseStudy}>
        {STUDIES.map(([id,label]) => <option key={id} value={id}>{label}</option>)}
      </select></label>
      <span>Each study keeps its own source and reading time.</span>
    </div>
    <OfflineBanner isOffline={isOffline} />
    <HeroSection ticker={normalizedTicker} spot={spot} data={data} dataAge={dataAge} dataFallback={dataFallback} />
    {family("levels", <>
      <div className="study-grid study-grid-three">
        <FlipZonesPanel ticker={normalizedTicker} spot={spot} />
        <NodeLifecyclePanel ticker={normalizedTicker} />
        <AirPocketsPanel ticker={normalizedTicker} />
      </div>
      <NodeConfluencePanel ticker={normalizedTicker} />
    </>)}
    {family("patterns", <div className="study-grid study-grid-three">
      <BeachBallIndicator ticker={normalizedTicker} />
      <ReverseRugIndicator ticker={normalizedTicker} />
      <RainbowRoadIndicator ticker={normalizedTicker} />
    </div>)}
    {family("income", <>
      <div className="study-grid study-grid-two">
        <div data-testid="hs-steal-dual-gex"><DualGEXBadge ticker={normalizedTicker} /></div>
        <div data-testid="hs-steal-iv-mid"><IVMidBadge ticker={normalizedTicker} width={6} /></div>
      </div>
      <div data-testid="hs-steal-wheel-income"><WheelIncomeScreenerPanel ticker={normalizedTicker} /></div>
    </>)}
    {family("history", <div data-testid="hs-row3-confluence-velocity" className="study-family-body">
      <ConfluenceVelocityRow ticker={normalizedTicker} />
      <div className="study-grid study-grid-two"><VelocityModeBadge ticker={normalizedTicker} /><TrinityConfluenceMeter /></div>
      <div data-testid="hs-steal-max-pain"><MaxPainBadge ticker={normalizedTicker} /></div>
      <div data-testid="hs-steal-max-pain-per-expiry-drift"><MaxPainPerExpiryDriftTile ticker={normalizedTicker} /></div>
    </div>)}
    {family("moves", <>
      <div className="study-grid study-grid-three"><StrikeConeBadge ticker={normalizedTicker} expiries={1} /><OpportunityBadge ticker={normalizedTicker} /><NewsBadge ticker={normalizedTicker} days={14} /></div>
      <div data-testid="hs-rnd-density-row"><RndDensityPanel ticker={normalizedTicker} expiries={1} /></div>
    </>)}
    {family("structure", <>
      <LazyRow><div className="study-grid study-grid-two"><RollingFloorsCeilingsPanel ticker={normalizedTicker} /><TugOfWarZonesPanel ticker={normalizedTicker} spot={spot} /></div></LazyRow>
      <LazyRow><div className="study-grid study-grid-two"><NodeClassificationPanel ticker={normalizedTicker} /><StackedNodesPanel ticker={normalizedTicker} /></div></LazyRow>
    </>)}
    {family("exposure", <LazyRow rootMargin="100px">
      <div className="study-grid study-grid-two">
        <ErrorBoundary><React.Suspense fallback={<div className="study-loading">Loading Vanna chart…</div>}><VannaChart ticker={normalizedTicker} spot={spot} /></React.Suspense></ErrorBoundary>
        <ErrorBoundary><React.Suspense fallback={<div className="study-loading">Loading Charm chart…</div>}><CharmChart ticker={normalizedTicker} spot={spot} /></React.Suspense></ErrorBoundary>
      </div>
      <div data-testid="hs-charm-decay"><CharmDecayPanel ticker={normalizedTicker} spot={spot} maxExpiries={6} /></div>
    </LazyRow>)}
    {family("briefing", <><BriefingStrip ticker={normalizedTicker} spot={spot} /><GammaRegimeBanner data={{ ...(data || {}), spot: spot ?? data?.spot }} /></>)}
  </div>;
}

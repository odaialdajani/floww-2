import React, { useEffect, useId, useMemo, useRef, useState } from "react";
import axios from "axios";
import { API } from "../../config/api";
import { wallPositionOf } from "../../lib/solsticeSelection";
import ExactContractReview from "../heatseeker/ExactContractReview";
import AskFlow from "../heatseeker/AskFlow";
import WallInspector from "../heatseeker/WallInspector";
import { chartTime } from "../heatseeker/recordedPriceChartData";
import { GroundedPublicReview } from "../public/PublicHandoffReview";

// Market selected-object inspector (OpenCode market-desktop-20261025).
// Root pixel critique 22:40 refinement — the Wall/Contract/Flow/Public tab
// strip sits DIRECTLY beneath the identity/close header and stays stable;
// only the body below it scrolls, and exactly ONE selected panel shows.
// The shared ReviewInspector is NOT modified (H1 writes Stock concurrently):
// this dock owns a Market-local tab strip with the same roles/keyboard
// contract and mounts the SAME existing panel consumers — WallInspector,
// ExactContractReview, AskFlow (the one assistant suite), GroundedPublicReview.
// The Contract/Flow/Public panels still mount ONLY on the deliberate
// "Review contracts" action: those components read/POST on mount, and an
// always-mounted panel would change request behavior.
//
// Every existing test surface is preserved verbatim: the dock root carries
// data-testid="triad-contract-drawer" exactly while that review action is
// open, the wall panel keeps triad-scenario/-zone/-readiness/-position/
// -blocker testids, the empty state keeps triad-no-wall, and repeated
// snapshot/UUID/formula strings live in one provenance details block with
// the readable LIVE/age/quality line staying outside it.

const SECTIONS = [["wall", "Wall"], ["contract", "Contract"], ["flow", "Flow"], ["publicAgent", "Public agent"]];

function fmtUsdCompact(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  const abs = Math.abs(n);
  const sign = n < 0 ? "-" : "";
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(abs >= 1e10 ? 0 : 1)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(abs >= 1e7 ? 0 : 1)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(abs >= 1e4 ? 0 : 1)}K`;
  return `${sign}$${abs.toFixed(0)}`;
}

function SelectedValues({ wall, adjNet, adjLabel }) {
  // Compact human-scale readings with the EXACT source value in the title —
  // no rescaling of the data, only of the display.
  const rows = [
    { key: "gross", label: "Raw gross", value: wall?.gross ?? null },
    { key: "net", label: "Raw net", value: wall?.net ?? null },
    { key: "adj", label: `Adj net · ${adjLabel}`, value: adjNet },
  ];
  return (
    <div className="tdk-values" data-testid="triad-dock-values">
      {rows.map(r => {
        // null/undefined/unreadable stay "—" — never coerced to a
        // fabricated 0 by Number(null).
        const num = typeof r.value === "number" && Number.isFinite(r.value) ? r.value : null;
        return (
          <div key={r.key} className="tdk-value" title={num == null ? "unavailable in this snapshot" : `exact value ${num}`}>
            <span className="tdk-value-label">{r.label}</span>
            <span className={`tdk-value-num${num != null ? num > 0 ? " pos" : num < 0 ? " neg" : "" : ""}`}>
              {num == null ? "—" : fmtUsdCompact(num)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function ScenarioCard({ wall, scenarios, spot, quality, onContracts, ticker, read, replay }) {
  const [first, second] = scenarios || [];
  // Position strip: spot marker against the wall zone on one shared scale.
  // Pure geometry (percent positions), no inferred levels.
  const pos = useMemo(() => {
    const low = Number(wall.low);
    const high = Number(wall.high);
    const sp = typeof spot === "number" && Number.isFinite(spot) ? spot : NaN;
    if (!Number.isFinite(low) || !Number.isFinite(high) || high <= low) return null;
    const lo = Number.isFinite(sp) ? Math.min(low, sp) : low;
    const hi = Number.isFinite(sp) ? Math.max(high, sp) : high;
    const pad = Math.max((hi - lo) * 0.5, Math.abs(hi) * 0.002, 0.01);
    const loP = lo - pad;
    const span = (hi - lo) + 2 * pad;
    const pct = (v) => Math.min(100, Math.max(0, ((v - loP) / span) * 100));
    return { z0: pct(low), z1: pct(high), sp: Number.isFinite(sp) ? pct(sp) : null };
  }, [wall, spot]);
  const wposNow = wallPositionOf(wall, spot);
  const posState = wposNow === "inside" ? "price inside wall"
    : wposNow === "below" ? "price above wall"
    : wposNow === "above" ? "price below wall" : null;
  return (
    <div className="triad-scenario" data-testid="triad-scenario">
      <div className="triad-scenario-zone" data-testid="triad-scenario-zone">
        Wall {wall.wall_id} · zone {wall.low}–{wall.high}
        {spot != null && wall.mid != null ? ` · ${Math.abs(spot - wall.mid).toFixed(1)} from mid` : ""}
      </div>
      <div className="triad-readiness" data-testid="triad-readiness" role="status">
        <strong>{read?.readiness || "Observe"}</strong><span>{read?.watch || "No directional watch"}</span>
        <small>{read?.reasons?.join(" · ")} · Conditional review only; adjusted sign is not a price forecast.</small>
      </div>
      {pos && (
        <div className="triad-position" data-testid="triad-position"
          title="Spot position against the wall zone (shared scale)">
          <div className="triad-position-rail">
            <div className="triad-position-zone" data-testid="triad-position-zone"
              style={{ left: `${pos.z0}%`, width: `${pos.z1 - pos.z0}%` }} />
            {pos.sp != null && (
              <div className="triad-position-spot" data-testid="triad-position-spot"
                style={{ left: `${pos.sp}%` }} />
            )}
          </div>
          <div className="triad-position-labels">
            <span>Below</span><span>Spot</span><span>Above</span>
          </div>
          {posState && (
            <div className="triad-position-state" data-testid="triad-position-state">{posState}</div>
          )}
        </div>
      )}
      {first ? (
        <div className="triad-scenario-side" data-testid="triad-scenario-first">
          <span className="triad-scenario-name">{first.name}</span>
          <span className="triad-scenario-confirm" title="Confirmation condition">Confirm: {first.confirmation}</span>
          <span className="triad-scenario-invalidate" title="Invalidation condition">Invalidate: {first.invalidation}</span>
        </div>
      ) : null}
      {second ? (
        <div className="triad-scenario-side" data-testid="triad-scenario-second">
          <span className="triad-scenario-name">{second.name}</span>
          <span className="triad-scenario-confirm" title="Confirmation condition">Confirm: {second.confirmation}</span>
          <span className="triad-scenario-invalidate" title="Invalidation condition">Invalidate: {second.invalidation}</span>
        </div>
      ) : null}
      {!first && (
        <div className="triad-scenario-empty">No scenario attached to this wall in the snapshot.</div>
      )}
      <div className="triad-scenario-blocker" data-testid="triad-blocker"
        title="Primary interpretation blocker">
        Blocker: {quality?.reasonCodes?.[0] || quality?.state || "none stated"}
      </div>
      {replay ? <div className="triad-price-empty">Replay: fresh price history is not requested. Use recorded interaction evidence.</div> : <WallPricePath ticker={ticker} wall={wall} spot={spot} />}
      <button className="triad-contracts-btn" data-testid="triad-contracts-btn"
        title="Review contracts at this wall (identity, delta, spread, quote age)"
        onClick={onContracts}>
        Review contracts
      </button>
    </div>
  );
}

function WallPricePath({ ticker, wall, spot }) {
  const [frames, setFrames] = React.useState(null);
  const [failed, setFailed] = React.useState(false);
  useEffect(() => {
    if (!ticker || !wall) return undefined;
    let cancelled = false;
    const ctrl = new AbortController();
    setFrames(null);
    setFailed(false);
    axios
      .get(`${API}/heatseeker/price-history/${encodeURIComponent(ticker)}`, {
        params: { days: 5 }, timeout: 30000, signal: ctrl.signal,
      })
      .then((r) => { if (!cancelled) setFrames(r?.data?.frames || []); })
      .catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; ctrl.abort(); };
  }, [ticker, wall?.wall_id]);
  const rows = useMemo(() => (Array.isArray(frames) ? frames : []).map(frame => {
    const at = typeof frame?.time === "string" && /(?:Z|[+-]\d{2}:\d{2})$/.test(frame.time) ? Date.parse(frame.time) : NaN;
    return {at, close: typeof frame?.close === "number" && Number.isFinite(frame.close) && frame.close > 0 ? frame.close : null};
  }), [frames]);
  const counts = new Map();
  for (const row of rows) if (Number.isFinite(row.at)) counts.set(row.at, (counts.get(row.at) || 0) + 1);
  const observed = rows.filter(row => Number.isFinite(row.at) && counts.get(row.at) === 1 && row.close != null);
  if (frames === null && !failed) return <div className="triad-price-loading">loading price path…</div>;
  if (failed) return <div className="triad-price-empty" data-testid="triad-price-empty">Price history unavailable for this symbol.</div>;
  if (!observed.length) return <div className="triad-price-empty" data-testid="triad-price-empty">No price candles for this period.</div>;
  const W = 300, H = 120, PAD = 6;
  const first = Math.min(...observed.map(row => row.at)), last = Math.max(...observed.map(row => row.at));
  const lo = Math.min(...observed.map(row => row.close)), hi = Math.max(...observed.map(row => row.close));
  const span = hi - lo || 1;
  const X = at => first === last ? W / 2 : PAD + (at - first) / (last - first) * (W - 2 * PAD);
  const Y = value => H - PAD - (value - lo) / span * (H - 2 * PAD);
  const segments = [];
  let segment = [], previous = null;
  for (const row of rows) {
    if (!Number.isFinite(row.at) || row.close == null || counts.get(row.at) !== 1 || (previous != null && row.at <= previous)) {
      if (segment.length) segments.push(segment);
      segment = []; previous = null; continue;
    }
    segment.push(row); previous = row.at;
  }
  if (segment.length) segments.push(segment);
  return <div className="triad-price" data-testid="triad-price-path">
    <p className="triad-price-caption">Current map reference: wall {wall.low}–{wall.high}{typeof spot === "number" && Number.isFinite(spot) ? ` · price ${spot.toFixed(2)}` : ""} — not historical candle-time levels.</p>
    <svg data-testid="triad-price-path-svg" data-first-at={new Date(first).toISOString()} data-last-at={new Date(last).toISOString()}
      viewBox={`0 0 ${W} ${H}`} width="100%" height="120" role="img" aria-label="Historical closes by recorded time; no historical wall inferred">
      {segments.filter(part => part.length > 1).map((part, i) => <polyline key={i} points={part.map(row => `${X(row.at).toFixed(1)},${Y(row.close).toFixed(1)}`).join(" ")} fill="none" stroke="#7dd3fc" strokeWidth="1.5" />)}
      {observed.map(row => <circle key={row.at} cx={X(row.at)} cy={Y(row.close)} r="1.5" fill="#7dd3fc"><title>{new Date(row.at).toISOString()} · {row.close}</title></circle>)}
    </svg>
    <div className="triad-price-caption" data-testid="triad-price-caption">
      {observed.length} closes · {chartTime(first, true)} → {chartTime(last, true)} · missing/ambiguous readings break the line. Current map references are not historical candle-time levels. VWAP unavailable (no verified source).
    </div>
  </div>;
}

// One readable identity/age/quality line — the exact snapshot id, formula,
// source and scope strings move into the closed details so the long live
// UUID/formula prose stops repeating through the narrative (root 22:40).
function ProvenanceLine({ data, replay, quality }) {
  return (
    <div className="tdk-provenance" data-testid="triad-dock-provenance">
      <span className="tdk-provenance-live">
        {replay ? "REPLAY" : "LIVE"}
        {" · quality "}{quality?.state || "unknown"}
        {data?.asof ? ` · generated ${chartTime(Date.parse(data.asof), true)}` : ""}
      </span>
      <details className="tdk-provenance-details">
        <summary title="Exact snapshot identity, formula, source and scope for this reading">Provenance</summary>
        <dl>
          <dt>Snapshot</dt><dd>{data?.snapshotId || "unknown"}</dd>
          <dt>Generated</dt><dd>{data?.asof || "time unknown"}</dd>
          <dt>Source</dt><dd>{data?.data_source || "unknown"}</dd>
          <dt>Formula</dt><dd>{data?.formula_version || data?.metrics?.formula_version || "unknown"}</dd>
          <dt>Market observation</dt><dd>{data?.event_time || data?.observed_at || "unknown"}</dd>
          <dt>Expiry scope</dt><dd>{data?.grid?.expiries?.join(", ") || "unknown"}</dd>
        </dl>
      </details>
    </div>
  );
}

function ReviewHint({ children }) {
  return <div className="tdk-hint">{children}</div>;
}

export default function MarketInspectorDock({
  ticker, data, cell, wall, scenario, scenarios, spot, quality, read, adjNet,
  adjLabel, metric, replay, drawerOpen, onClose, closeRef, selectionScope,
  onSelection, selectionRevision, onContracts,
}) {
  const id = useId();
  const tabsRef = useRef([]);
  const [active, setActive] = useState("wall");
  // The deliberate review action opens the exact-contract panel.
  const startReview = () => { onContracts(); setActive("contract"); };
  // Escape closes the open review / overlay (stable bounded close).
  useEffect(() => {
    const close = e => { if (e.key === "Escape" && drawerOpen) onClose(); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [drawerOpen, onClose]);
  // Same tab keyboard contract as the shared inspector: arrows/Home/End.
  const onTabKey = (event, index) => {
    let next;
    if (event.key === "ArrowRight") next = (index + 1) % SECTIONS.length;
    else if (event.key === "ArrowLeft") next = (index + SECTIONS.length - 1) % SECTIONS.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = SECTIONS.length - 1;
    else return;
    event.preventDefault();
    event.stopPropagation();
    setActive(SECTIONS[next][0]);
    tabsRef.current[next]?.focus();
  };
  const closeDisclosure = event => {
    if (event.key !== "Escape" || event.defaultPrevented) return;
    const disclosure = event.target.closest?.("details[open]");
    if (!disclosure || !event.currentTarget.contains(disclosure)) return;
    event.preventDefault();
    event.stopPropagation();
    disclosure.open = false;
    disclosure.querySelector(":scope > summary")?.focus();
  };
  const identity = wall ? `Wall ${wall.low}–${wall.high}`
    : cell?.strike != null ? `Strike ${cell.strike}` : "Nothing selected";
  const wallPanel = !wall ? (
    <div className="tdk-empty" data-testid="triad-no-wall">
      {cell?.strike != null ? (
        <strong>Strike {cell.strike} selected — no structural wall at this strike.</strong>
      ) : (
        <strong>Nothing selected yet.</strong>
      )}
      <span>Click a cell in either map — or a wall chip below the maps — and its readings, scenarios and the
        Wall → Contract → Flow → Public brief review open here, beside the comparison.</span>
      <small>No structural wall selected — pick a cell in either pane. An adjusted-only peak with no
        corresponding GEX wall will say so here rather than inheriting another wall's story.</small>
    </div>
  ) : (
    <>
      <SelectedValues wall={wall} adjNet={adjNet} adjLabel={adjLabel} />
      <ScenarioCard wall={wall} scenarios={scenarios} spot={spot} quality={quality}
        onContracts={startReview} ticker={ticker} read={read} replay={replay} />
      <ProvenanceLine data={data} replay={replay} quality={quality} />
    </>
  );
  const contractPanel = drawerOpen
    ? <ExactContractReview key={`${ticker}|${wall?.wall_id || ""}|${data?.snapshotId || ""}`} ticker={ticker} data={data} wall={wall} cell={cell} replay={replay} selectionScope={selectionScope} onSelection={onSelection} />
    : <ReviewHint>Exact contract rows load with the “Review contracts” action on the Wall tab — identity, delta, spread and quote age, with recorded candidates before any exact-detail request.</ReviewHint>;
  const flowPanel = drawerOpen
    ? <>
      <h3>Flow · selected reading</h3>
      <dl className="review-inspector-context">
        <dt>Stock / wall</dt><dd>{ticker} · {wall?.wall_id || "No classified wall"}</dd>
        <dt>Snapshot</dt><dd>{data?.snapshotId || "Unknown"}</dd>
        <dt>Market observation</dt><dd>{data?.event_time || data?.observed_at || "Unknown"}</dd>
        <dt>Snapshot time</dt><dd>{data?.asof || "Unknown"} · {replay ? "Recorded" : "Live request"}</dd>
      </dl>
      <p>The same Ask Flow assistant explains this selection. Opening a step does not request research or prepare an order.</p>
      <AskFlow subject={`${ticker} · exact contract review`} overlayMetric={metric} displayMode={replay ? "replay" : "live"} compact />
    </>
    : <ReviewHint>Ask Flow for this selection loads with the “Review contracts” action on the Wall tab. Opening a step never requests research or prepares an order.</ReviewHint>;
  const publicPanel = drawerOpen
    ? <><h3>Public agent · reviewed draft</h3><p>A copied brief is not delivery or activation. Review the workflow in Public before any separately approved activation.</p><GroundedPublicReview /></>
    : <ReviewHint>The editable Public brief for this selection loads with the “Review contracts” action on the Wall tab. A copied brief is not delivery or activation.</ReviewHint>;
  const panels = { wall: wallPanel, contract: contractPanel, flow: flowPanel, publicAgent: publicPanel };
  return (
    <aside className="tdk-dock"
      data-testid={drawerOpen ? "triad-contract-drawer" : "triad-inspector-dock"}
      role="dialog" aria-label={drawerOpen ? "Contract review" : "Selected object inspector"}>
      <div className="tdk-dock-head">
        <span className="tdk-dock-title">Selected</span>
        <span className="tdk-dock-id" data-testid="triad-dock-id">{ticker} · {identity}</span>
        <button ref={closeRef} className="tdk-dock-close" onClick={onClose}
          data-testid="triad-drawer-close" aria-label="Close contract review">✕</button>
      </div>
      {/* Stable tab strip directly beneath the identity/close row; only the
          body below it scrolls (root 22:40 critique). */}
      <div className="tdk-dock-tabs" role="tablist" aria-label="Inspector sections" onKeyDown={closeDisclosure}>
        {SECTIONS.map(([key, label], index) => (
          <button key={key} ref={el => { tabsRef.current[index] = el; }}
            type="button" role="tab" id={`${id}-${key}-tab`} aria-controls={`${id}-${key}-panel`}
            aria-selected={active === key} tabIndex={active === key ? 0 : -1}
            onClick={() => setActive(key)} onKeyDown={event => onTabKey(event, index)}>{label}</button>
        ))}
      </div>
      <div className="tdk-dock-body">
        {SECTIONS.map(([key]) => (
          <section key={key} role="tabpanel" className="tdk-dock-panel"
            id={`${id}-${key}-panel`} aria-labelledby={`${id}-${key}-tab`} hidden={active !== key} tabIndex={0}>
            {panels[key]}
          </section>
        ))}
      </div>
    </aside>
  );
}

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import { API } from "../../config/api";
import { usePublishScreenContext } from "../../agent/useScreenContext";
import SkylitHeatmapGrid from "./SkylitHeatmapGrid";
import WallInspector from "./WallInspector";
import ExactContractReview from "./ExactContractReview";
import AskLodestar from "./AskLodestar";
import { mapSurface } from "./shownMapStrikes";

/** Independent canonical panes; never projects another symbol onto SPY's strike rail. */
export default function SolsticeSymbolMaps({ ticker = "SPY", data, metric = "raw", viewMode = "gex", mode = "day", expiries = 4, dte = null, replay = false, locked = false }) {
  const [names, setNames] = useState(() => [...new Set([ticker, ticker === "QQQ" ? "SPY" : "QQQ"])]);
  const [active, setActive] = useState(ticker);
  const [packets, setPackets] = useState({});
  const [errors, setErrors] = useState({});
  const [selected, setSelected] = useState(null);
  const [review, setReview] = useState(false);
  const [ranges, setRanges] = useState({});
  const frozen = useRef({});
  const priorLock = useRef(false);
  const generation = useRef(0);
  const nameKey = names.join("|");
  const scopeKey = `${nameKey}|${mode}|${expiries}|${dte}|${metric}|${viewMode}|${replay}`;
  useEffect(() => {
    if (data?.ticker === ticker) setPackets(p => ({ ...p, [ticker]: data }));
  }, [ticker, data]);
  useEffect(() => {
    const gen = ++generation.current;
    const ctrl = new AbortController();
    setSelected(null); setReview(false); setErrors({});
    frozen.current = {};
    if (replay) {
      setPackets(data?.ticker === ticker ? { [ticker]: data } : {});
      return undefined;
    }
    const others = names.filter(n => n !== ticker);
    setPackets(data?.ticker === ticker ? { [ticker]: data } : {});
    for (const name of others) axios.get(`${API}/heatmap/${encodeURIComponent(name)}`, {
      params: { mode, expiries, ...(dte != null ? { dte } : {}) }, signal: ctrl.signal, timeout: 45000,
    }).then(r => {
      if (gen !== generation.current || ctrl.signal.aborted) return;
      if (r?.data?.ticker !== name || !r.data.grid?.strikes?.length) throw new Error("No matching symbol observation");
      setPackets(p => ({ ...p, [name]: r.data }));
    }).catch(() => { if (gen === generation.current && !ctrl.signal.aborted) setErrors(e => ({ ...e, [name]: "Source / entitlement unavailable" })); });
    return () => { generation.current++; ctrl.abort(); };
    // Primary packet updates are copied above; no second poller or fetch on cell/basis selection.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nameKey, mode, expiries, dte, replay]);
  if (locked && !priorLock.current) frozen.current = { ...ranges };
  if (!locked) frozen.current = {};
  priorLock.current = locked;
  const scaleCallbacks = useMemo(() => Object.fromEntries(names.map(n => [n, range => setRanges(prev =>
    prev[n]?.min === range.min && prev[n]?.max === range.max ? prev : { ...prev, [n]: range })])), [nameKey]);
  useEffect(() => { frozen.current = {}; }, [scopeKey]);
  const packet = packets[active];
  const cell = selected?.ticker === active ? selected : null;
  const wall = cell ? (packet?.metrics?.walls || []).find(w => w.wall_id === cell.wall_id) || null : null;
  const surface = mapSurface(packet, viewMode, metric);
  usePublishScreenContext(packet ? { contextVersion: 2, page: "heatseeker", ticker: active, metric: viewMode, overlayMetric: metric,
    displayMode: replay ? "replay" : "live", snapshotId: packet.snapshotId || null, provider: packet.data_source || null,
    formula: packet.formula_version || null, activePane: viewMode, mapQuery: packet.map_query || null, mapVersion: packet.asof || null,
    mapStrikes: surface.strikes, mapExpiries: surface.expiries, selectedWall: cell?.wall_id || null,
    selectedStrike: cell?.strike ?? null, selectedExpiry: cell?.colKey || null } : null);
  const select = useCallback((name, strike, colKey) => {
    const w = (packets[name]?.metrics?.walls || []).find(w => strike >= w.low && strike <= w.high);
    setActive(name); setSelected({ ticker: name, strike, colKey, wall_id: w?.wall_id || null });
  }, [packets]);
  useEffect(() => {
    if (!review) return undefined;
    const close = e => { if (e.key === "Escape") setReview(false); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [review]);
  return <div className="solstice-symbol-workspace" data-testid="solstice-symbol-maps">
    <div className="solstice-symbol-heading">
      <span>Independent symbol axes · active inspector: {active} · each timestamp/scope disclosed</span>
      <button onClick={() => setNames([...new Set([ticker, ticker === "QQQ" ? "SPY" : "QQQ"])])}>Two symbols</button>
      <button onClick={() => setNames([...new Set([ticker, "SPY", "QQQ", "^SPX", "IWM"])].slice(0, 4))}>Four symbols</button>
      {names.map(n => <button key={n} aria-pressed={active === n} onClick={() => { setActive(n); setReview(false); }}>{n}</button>)}
      <button disabled={!cell || !packet} onClick={() => setReview(true)}>Review selected wall</button>
    </div>
    <div className="solstice-symbol-body">
      <div className="solstice-symbol-grid">{names.map(name => {
        const p = packets[name];
        const range = locked ? frozen.current[name] : null;
        return <section className={`solstice-symbol-pane${active === name ? " active" : ""}`} key={name} data-testid={`symbol-map-${name}`}>
          <header><button onClick={() => { setActive(name); setReview(false); }}>{name}</button> · {viewMode.toUpperCase()} / {metric}
            <small>{p?.snapshotId || "observation unavailable"} · {p?.asof || "timestamp unknown"} · {p?.data_source || "source unknown"}</small>
            <small>{p?.grid?.expiries?.join(", ") || "expiry scope unavailable"} · {p?.quality?.state || "quality unknown"}
              {locked ? range ? " · scale locked for this pane" : " · no captured scale" : " · pane-relative scale"}</small></header>
          {p ? <SkylitHeatmapGrid data={p} spot={p.spot ?? null} ticker={name} metric={metric} viewMode={viewMode}
            scale={range ? { ...range, locked: true } : null} onScaleReady={scaleCallbacks[name]}
            selected={cell?.ticker === name ? { strike: cell.strike, expiry: cell.colKey } : null}
            wallBand={active === name ? wall : null} onCellClick={(s,e) => select(name,s,e)} /> : <p role="status">
            {replay ? "Recorded frame unavailable — no live substitution" : errors[name]
              ? `${name.includes("SPX") ? "SPX unavailable · entitlement not proven" : name + " unavailable"} · ${errors[name]}` : "Loading bounded symbol scope…"}</p>}
        </section>;
      })}</div>
      <aside className="solstice-symbol-inspector" data-testid="symbol-map-inspector"><strong>{active} · selected wall</strong>
        <p>{packet?.quality?.state || "unavailable"} · {(packet?.quality?.reasonCodes || []).join(", ") || "source age / coverage inspectable in packet"}</p>
        <WallInspector wall={wall} metrics={packet?.metrics} grids={packet?.metrics?.grids} displayGrid={packet?.grid}
          quality={packet?.quality} interaction={(packet?.interactions || []).find(i => i.wall_id === wall?.wall_id)}
          metric={metric} snapshotId={packet?.snapshotId} replay={replay} />
        <button disabled={!cell || !packet} onClick={() => setReview(true)}>Review exact contract</button>
        <AskLodestar subject={`${active} · ${cell?.wall_id || "no selected wall"}`} overlayMetric={metric} displayMode={replay ? "replay" : "live"} compact />
      </aside>
    </div>
    {review && <div className="skylit-drawer" role="dialog" aria-label={`${active} contract review`}>
      <button autoFocus onClick={() => setReview(false)} aria-label="Close contract review">Close</button>
      <WallInspector wall={wall} metrics={packet?.metrics} grids={packet?.metrics?.grids} displayGrid={packet?.grid}
        quality={packet?.quality} metric={metric} snapshotId={packet?.snapshotId} replay={replay} />
      <ExactContractReview ticker={active} data={packet} wall={wall} cell={cell} replay={replay} />
    </div>}
  </div>;
}

import React, { memo, useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import { API as BACKEND_API } from "../../config/api";
import { replayToDisplay, stepReplay } from "../../lib/solsticeReplay";

/**
 * ReplayStrip — actual guided replay (P09/R4-15, R5-B isolation).
 * Loads the manifest, steps chronologically through RECORDED snapshots, and
 * hands full snapshot content to the grid via onReplay (never counts-only).
 * R5-B guards: requests are generation-checked + aborted; manifest, selection
 * and in-flight work reset on ticker change; a response arriving after exit
 * ("Live") or after a ticker switch is discarded, never rendered.
 */
function ReplayStrip({ ticker = "SPY", onReplay = null, openRequest = null }) {
  const [manifest, setManifest] = useState(null);
  const [compare, setCompare] = useState(null);
  const [loading, setLoading] = useState(false);
  const [currentId, setCurrentId] = useState(null);
  const [replayAsOf, setReplayAsOf] = useState(null);
  const [health, setHealth] = useState(null);
  const genRef = useRef(0);
  // Ticker switch clears replay state: no old-ticker snapshot may render
  // under the new heading, and in-flight work is invalidated.
  useEffect(() => {
    genRef.current += 1;
    setManifest(null);
    setCompare(null);
    setCurrentId(null);
    setReplayAsOf(null);
    setHealth(null);
  }, [ticker]);
  const load = useCallback(async () => {
    const myGen = ++genRef.current;
    const myTicker = ticker;
    setLoading(true);
    try {
      const r = await axios.get(`${BACKEND_API}/solstice/manifest/${encodeURIComponent(ticker)}`, { timeout: 15000 });
      // Discard late manifest/health after a ticker switch or exit.
      if (genRef.current !== myGen || myTicker !== ticker) return;
      setManifest(r.data);
    } catch (e) {
      if (genRef.current !== myGen) return;
      setManifest({ error: "manifest_unavailable" });
    } finally {
      if (genRef.current === myGen) setLoading(false);
    }
    // R6-3 recorder badge: actual backing + durability, never path inference.
    try {
      const h = await axios.get(`${BACKEND_API}/solstice/recorder_health`, { timeout: 15000 });
      if (genRef.current !== myGen || myTicker !== ticker) return;
      setHealth(h.data);
    } catch (e) {
      if (genRef.current !== myGen) return;
      setHealth({ error: "health_unavailable" });
    }
  }, [ticker]);
  const compareLastTwo = useCallback(async () => {
    const myGen = ++genRef.current;
    const myTicker = ticker;
    setLoading(true);
    try {
      const r = await axios.get(`${BACKEND_API}/solstice/attribute/${encodeURIComponent(ticker)}`, { timeout: 15000 });
      if (genRef.current !== myGen || myTicker !== ticker) return;
      setCompare(r.data);
    } catch (e) {
      if (genRef.current !== myGen) return;
      setCompare({ status: "error" });
    } finally {
      if (genRef.current === myGen) setLoading(false);
    }
  }, [ticker]);
  const snaps = manifest?.snapshots || [];
  const openSnap = useCallback(async (id) => {
    if (!id || !onReplay) return;
    const myGen = ++genRef.current;
    const myTicker = ticker;
    const ctrl = new AbortController();
    setLoading(true);
    try {
      const r = await axios.get(`${BACKEND_API}/solstice/replay/${encodeURIComponent(id)}`, { timeout: 15000, signal: ctrl.signal });
      // Discard late responses: ticker switched or replay exited since request.
      if (genRef.current !== myGen || myTicker !== ticker) return;
      const disp = replayToDisplay(r.data, myTicker);
      if (disp) {
        setCurrentId(id);
        setReplayAsOf(disp.asof);
        onReplay(disp);
      }
    } catch (e) {
      /* replay unavailable — stay live, never partial grid */
    } finally {
      if (genRef.current === myGen) setLoading(false);
    }
  }, [ticker, onReplay]);
  const step = useCallback((dir) => {
    const nxt = stepReplay(snaps, currentId, dir);
    if (nxt) openSnap(nxt.id);
  }, [snaps, currentId, openSnap]);
  const exitReplay = useCallback(() => {
    // Invalidate in-flight snapshot fetches so a late response can never
    // re-enter replay after the user chose Live.
    genRef.current += 1;
    setCurrentId(null);
    setReplayAsOf(null);
    if (onReplay) onReplay(null);
  }, [onReplay]);
  // R8-04: external replay jump (Next-to-review list). Same generation
  // guards as stepping: ticker switches and exits invalidate the request.
  const lastOpened = useRef(null);
  useEffect(() => {
    if (!openRequest || !openRequest.id) return;
    const key = `${ticker}:${openRequest.id}:${openRequest.nonce ?? 0}`;
    if (lastOpened.current === key) return;
    lastOpened.current = key;
    openSnap(openRequest.id);
  }, [openRequest, openSnap, ticker]);
  return (
    <div className="skylit-replay-strip" data-testid="solstice-replay-strip"
      title="Deterministic replay — what was available at decision time">
      <button className="skylit-trade-mode-btn" onClick={load} data-testid="solstice-replay-load"
        title="Load today's recorded session manifest">
        {loading ? "Loading…" : `Replay ${ticker}`}
      </button>
      <button className="skylit-trade-mode-btn" onClick={compareLastTwo} data-testid="solstice-compare-btn"
        title="Session change window: wall-level change between the last two recorded snapshots (descriptive, not the spot/IV/time/OI counterfactual)">
        Compare last two
      </button>
      {snaps.length > 0 && (
        <>
          <button className="skylit-trade-mode-btn" onClick={() => step(-1)} data-testid="solstice-replay-prev" title="Step to earlier recorded snapshot">‹ Prev</button>
          <button className="skylit-trade-mode-btn" onClick={() => step(1)} data-testid="solstice-replay-next" title="Step to later recorded snapshot (never beyond the last record)">Next ›</button>
        </>
      )}
      {currentId && (
        <button className="skylit-trade-mode-btn" onClick={exitReplay} data-testid="solstice-replay-exit" title="Return to live deliberately">
          Live
        </button>
      )}
      {manifest && !manifest.error && (
        <span data-testid="solstice-replay-count" title="Recorded snapshots (gaps = missing capture, not missing market)">
          {snaps.length} snapshots{snaps.length === 0 ? " — no capture yet" : ""}
          {currentId ? ` · REPLAY ${replayAsOf || currentId}` : ""}
        </span>
      )}
      {health && !health.error && (
        <span
          data-testid="solstice-recorder-badge"
          title={health.durable ? "File-backed durable recorder" : "Memory fallback — analytics run, durable capture NOT claimed"}
        >
          REC {health.durable ? "● durable" : "○ memory"}
        </span>
      )}
      {manifest?.error && <span>replay unavailable</span>}
      {compare && compare.status === "ok" && (
        <span data-testid="solstice-compare-result"
          title={`Prior ${compare.from?.asof || "?"} → current ${compare.to?.asof || "?"}; coarse wall-level comparison; use the counterfactual for spot/IV/time/OI decomposition`}>
          {(compare.from?.asof || "?").slice(11, 16)}→{(compare.to?.asof || "?").slice(11, 16)} · Δ {compare.strike_deltas?.length || 0} strikes · +{(compare.walls_added || []).length}/-{(compare.walls_removed || []).length} walls · vol Δ {compare.volume_deltas?.length || 0}{compare.volume_rebased?.length ? ` · rebased ${compare.volume_rebased.length}` : ""}
        </span>
      )}
      {compare && compare.status === "history_unavailable" && (
        <span data-testid="solstice-compare-empty">need 2+ snapshots</span>
      )}
    </div>
  );
}

export default memo(ReplayStrip);

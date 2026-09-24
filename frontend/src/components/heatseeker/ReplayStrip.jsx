import React, { memo, useCallback, useState } from "react";
import axios from "axios";
import { API as BACKEND_API } from "../../config/api";
import { replayToDisplay, stepReplay } from "../../lib/solsticeReplay";

/**
 * ReplayStrip — actual guided replay (P09/R4-15).
 * Loads the manifest, steps chronologically through RECORDED snapshots, and
 * hands full snapshot content to the grid via onReplay (never counts-only).
 * Live refresh must be ignored while replay is active; return to live is
 * deliberate via onReplay(null).
 */
function ReplayStrip({ ticker = "SPY", onReplay = null }) {
  const [manifest, setManifest] = useState(null);
  const [compare, setCompare] = useState(null);
  const [loading, setLoading] = useState(false);
  const [currentId, setCurrentId] = useState(null);
  const [replayAsOf, setReplayAsOf] = useState(null);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${BACKEND_API}/solstice/manifest/${encodeURIComponent(ticker)}`, { timeout: 15000 });
      setManifest(r.data);
    } catch (e) {
      setManifest({ error: "manifest_unavailable" });
    } finally {
      setLoading(false);
    }
  }, [ticker]);
  const compareLastTwo = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${BACKEND_API}/solstice/attribute/${encodeURIComponent(ticker)}`, { timeout: 15000 });
      setCompare(r.data);
    } catch (e) {
      setCompare({ status: "error" });
    } finally {
      setLoading(false);
    }
  }, [ticker]);
  const snaps = manifest?.snapshots || [];
  const openSnap = useCallback(async (id) => {
    if (!id || !onReplay) return;
    setLoading(true);
    try {
      const r = await axios.get(`${BACKEND_API}/solstice/replay/${encodeURIComponent(id)}`, { timeout: 15000 });
      const disp = replayToDisplay(r.data, ticker);
      if (disp) {
        setCurrentId(id);
        setReplayAsOf(disp.asof);
        onReplay(disp);
      }
    } catch (e) {
      /* replay unavailable — stay live, never partial grid */
    } finally {
      setLoading(false);
    }
  }, [ticker, onReplay]);
  const step = useCallback((dir) => {
    const nxt = stepReplay(snaps, currentId, dir);
    if (nxt) openSnap(nxt.id);
  }, [snaps, currentId, openSnap]);
  const exitReplay = useCallback(() => {
    setCurrentId(null);
    setReplayAsOf(null);
    if (onReplay) onReplay(null);
  }, [onReplay]);
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
      {manifest?.error && <span>replay unavailable</span>}
      {compare && compare.status === "ok" && (
        <span data-testid="solstice-compare-result"
          title="Coarse wall-level comparison; use the counterfactual for spot/IV/time/OI decomposition">
          Δ {compare.strike_deltas?.length || 0} strikes · +{(compare.walls_added || []).length}/-{(compare.walls_removed || []).length} walls · vol Δ {compare.volume_deltas?.length || 0}{compare.volume_rebased?.length ? ` · rebased ${compare.volume_rebased.length}` : ""}
        </span>
      )}
      {compare && compare.status === "history_unavailable" && (
        <span data-testid="solstice-compare-empty">need 2+ snapshots</span>
      )}
    </div>
  );
}

export default memo(ReplayStrip);

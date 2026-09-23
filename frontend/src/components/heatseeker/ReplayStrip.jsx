import React, { memo, useCallback, useState } from "react";
import axios from "axios";
import { API as BACKEND_API } from "../../config/api";

/**
 * ReplayStrip — compact replay/event strip + data status (T23).
 * Guided replay: loads the session manifest, steps through recorded snapshot
 * IDs in order. Late events never rewrite issued decisions (available-at).
 */
function ReplayStrip({ ticker = "SPY" }) {
  const [manifest, setManifest] = useState(null);
  const [loading, setLoading] = useState(false);
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
  const snaps = manifest?.snapshots || [];
  return (
    <div className="skylit-replay-strip" data-testid="solstice-replay-strip"
      title="Deterministic replay — what was available at decision time">
      <button className="skylit-trade-mode-btn" onClick={load} data-testid="solstice-replay-load"
        title="Load today's recorded session manifest">
        {loading ? "Loading…" : `Replay ${ticker}`}
      </button>
      {manifest && !manifest.error && (
        <span data-testid="solstice-replay-count" title="Recorded snapshots (gaps = missing capture, not missing market)">
          {snaps.length} snapshots{snaps.length === 0 ? " — no capture yet" : ""}
        </span>
      )}
      {manifest?.error && <span>replay unavailable</span>}
    </div>
  );
}

export default memo(ReplayStrip);

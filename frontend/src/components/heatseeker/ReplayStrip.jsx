import React, { memo, useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import { API as BACKEND_API } from "../../config/api";
import { replayToDisplay, stepReplay, replayIndexOf } from "../../lib/solsticeReplay";

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
  const [day, setDay] = useState("");
  const [refusal, setRefusal] = useState(null);
  const [sessions, setSessions] = useState(null);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const sessionController = useRef(null);
  const sessionGeneration = useRef(0);
  useEffect(() => {
    sessionGeneration.current += 1;
    setSessions(null);
    setSessionsLoading(false);
    setDay("");
    return () => { sessionGeneration.current += 1; sessionController.current?.abort(); };
  }, [ticker]);
  const loadSessions = useCallback(async () => {
    const generation = ++sessionGeneration.current;
    sessionController.current?.abort();
    const ctrl = new AbortController();
    sessionController.current = ctrl;
    setSessions(null);
    setSessionsLoading(true);
    try {
      const { data } = await axios.get(`${BACKEND_API}/solstice/price-paths/sessions?ticker=${encodeURIComponent(ticker)}`, { timeout: 15000, signal: ctrl.signal });
      if (sessionGeneration.current !== generation) return;
      const error = data?.error || (data?.version !== "coverage-read.v1" ? "COVERAGE_VERSION_UNSUPPORTED"
        : data.ticker !== ticker ? "SESSION_IDENTITY_MISMATCH"
        : !Array.isArray(data.days) || data.n_days !== data.days.length || data.days.some(entry =>
          !/^\d{4}-\d{2}-\d{2}$/.test(entry?.date || "") || !Number.isInteger(entry.n_snapshots) || entry.n_snapshots < 1
          || !entry.latest_snapshot_id || !entry.first_asof || !entry.last_asof)
          ? "SESSION_INDEX_UNAVAILABLE" : null);
      setSessions(error ? { error } : data);
    } catch (e) {
      if (sessionGeneration.current === generation) setSessions({ error: "SESSION_READ_FAILED" });
    } finally {
      if (sessionGeneration.current === generation) setSessionsLoading(false);
    }
  }, [ticker]);
  const requestController = useRef(null);
  const beginRequest = useCallback(() => {
    requestController.current?.abort();
    const ctrl = new AbortController();
    requestController.current = ctrl;
    return ctrl;
  }, []);
  // O3 Play: auto-advance through RECORDED snapshots only. Chained timeouts
  // (not an interval) so each step waits for the previous snapshot to land;
  // reaching the last record stops playback by itself. Never arms live.
  const [playing, setPlaying] = useState(false);
  const curIdRef = useRef(currentId);
  curIdRef.current = currentId;
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
    setPlaying(false);
    setLoading(false);
    setRefusal(null);
    return () => { genRef.current += 1; requestController.current?.abort(); };
  }, [ticker, day]);
  const load = useCallback(async () => {
    const myGen = ++genRef.current;
    const myTicker = ticker;
    const ctrl = beginRequest();
    setLoading(true);
    setPlaying(false);
    setCompare(null);
    setRefusal(null);
    try {
      const query = day ? `?day=${encodeURIComponent(day)}` : "";
      const r = await axios.get(`${BACKEND_API}/solstice/manifest/${encodeURIComponent(ticker)}${query}`, { timeout: 15000, signal: ctrl.signal });
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
      const h = await axios.get(`${BACKEND_API}/solstice/recorder_health`, { timeout: 15000, signal: ctrl.signal });
      if (genRef.current !== myGen || myTicker !== ticker) return;
      setHealth(h.data);
    } catch (e) {
      if (genRef.current !== myGen) return;
      setHealth({ error: "health_unavailable" });
    }
  }, [ticker, day, beginRequest]);
  const compareLastTwo = useCallback(async () => {
    const myGen = ++genRef.current;
    const myTicker = ticker;
    const ctrl = beginRequest();
    setLoading(true);
    setPlaying(false);
    setCompare(null);
    try {
      const query = day ? `?day=${encodeURIComponent(day)}` : "";
      const r = await axios.get(`${BACKEND_API}/solstice/attribute/${encodeURIComponent(ticker)}${query}`, { timeout: 15000, signal: ctrl.signal });
      if (genRef.current !== myGen || myTicker !== ticker) return;
      if (r.data?.status !== "ok") { setCompare(r.data || { status: "unavailable", reason: "COMPARISON_UNAVAILABLE" }); return; }
      const baseline = r.data.from?.id, snapshot = r.data.to?.id;
      if (!baseline || !snapshot || r.data.ticker !== ticker || (day && r.data.day !== day)) {
        setCompare({ status: "unavailable", reason: "COMPARISON_IDENTITY_MISMATCH" }); return;
      }
      // Attribute supplies arithmetic; only the owning-pair gate can admit it.
      const { data: admission } = await axios.get(`${BACKEND_API}/solstice/price-paths/comparable?baseline_id=${encodeURIComponent(baseline)}&snapshot_id=${encodeURIComponent(snapshot)}`, { timeout: 15000, signal: ctrl.signal });
      if (genRef.current !== myGen) return;
      const reason = admission?.version !== "coverage-read.v1" ? "COVERAGE_VERSION_UNSUPPORTED"
        : admission.admitted !== true ? admission.reason || "COMPARISON_NOT_ADMITTED"
        : admission.baseline_id !== baseline || admission.snapshot_id !== snapshot ? "COMPARISON_IDENTITY_MISMATCH" : null;
      setCompare(reason ? { status: "unavailable", reason, detail: admission?.detail } : r.data);
    } catch (e) {
      if (genRef.current !== myGen) return;
      setCompare({ status: "error" });
    } finally {
      if (genRef.current === myGen) setLoading(false);
    }
  }, [ticker, day, beginRequest]);
  const snaps = manifest?.snapshots || [];
  const openSnap = useCallback(async (id) => {
    if (!id || !onReplay) return;
    const myGen = ++genRef.current;
    const myTicker = ticker;
    const ctrl = beginRequest();
    setLoading(true);
    setCompare(null);
    setRefusal(null);
    try {
      const r = await axios.get(`${BACKEND_API}/solstice/replay/${encodeURIComponent(id)}`, { timeout: 15000, signal: ctrl.signal });
      // Discard late responses: ticker switched or replay exited since request.
      if (genRef.current !== myGen || myTicker !== ticker) return;
      const disp = replayToDisplay(r.data, myTicker);
      if (disp && disp.snapshotId === id) {
        setCurrentId(id);
        setReplayAsOf(disp.asof);
        onReplay(disp);
      } else {
        setPlaying(false);
        setRefusal(disp ? "RECORD_IDENTITY_MISMATCH" : "REPLAY_ENVELOPE_UNAVAILABLE");
      }
    } catch (e) {
      if (genRef.current === myGen) {
        setPlaying(false);
        setRefusal("REPLAY_READ_FAILED — previous display retained; no live substitution");
      }
    } finally {
      if (genRef.current === myGen) setLoading(false);
    }
  }, [ticker, onReplay, beginRequest]);
  const step = useCallback((dir) => {
    const nxt = stepReplay(snaps, currentId, dir);
    if (nxt) openSnap(nxt.id);
  }, [snaps, currentId, openSnap]);
  const exitReplay = useCallback(() => {
    // Invalidate in-flight snapshot fetches so a late response can never
    // re-enter replay after the user chose Live.
    genRef.current += 1;
    requestController.current?.abort();
    sessionGeneration.current += 1;
    sessionController.current?.abort();
    setSessionsLoading(false);
    setLoading(false);
    setCompare(null);
    setRefusal(null);
    setCurrentId(null);
    setReplayAsOf(null);
    setPlaying(false);
    if (onReplay) onReplay(null);
  }, [onReplay]);
  const stepOnce = useCallback(() => {
    const nxt = stepReplay(snaps, curIdRef.current, 1);
    if (nxt) {
      openSnap(nxt.id);
      return true;
    }
    setPlaying(false);
    return false;
  }, [snaps, openSnap]);
  useEffect(() => {
    if (!playing || loading) return undefined;
    if (currentId && replayIndexOf(snaps, currentId) >= snaps.length - 1) {
      setPlaying(false);
      return undefined;
    }
    const id = setTimeout(stepOnce, 2000);
    return () => clearTimeout(id);
  }, [playing, loading, currentId, snaps, stepOnce]);
  const togglePlay = useCallback(() => {
    if (playing) {
      setPlaying(false);
      return;
    }
    if (stepOnce()) setPlaying(true);
  }, [playing, stepOnce]);
  const scrubIndex = replayIndexOf(snaps, currentId);
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
      <button className="skylit-trade-mode-btn" onClick={loadSessions} disabled={sessionsLoading}>Stored sessions</button>
      {sessionsLoading && <span role="status">Reading stored sessions…</span>}
      {sessions && <span role="status" data-testid="solstice-session-status">{sessions.error || (sessions.days.length ? `${sessions.days.length} stored sessions · America/New_York` : "No stored sessions — capture not established")}</span>}
      {sessions?.days?.length > 0 && <label>Recorded <select aria-label="Recorded sessions" value={sessions.days.some(entry => entry.date === day) ? day : ""}
        onChange={e => { exitReplay(); setDay(e.target.value); }}>
        <option value="">Choose a stored session</option>
        {sessions.days.map(entry => <option key={entry.date} value={entry.date}>{entry.date} · {entry.n_snapshots} observations</option>)}
      </select></label>}
      <label>Session <input type="date" aria-label="Stored session date" value={day}
        onChange={e => { exitReplay(); setDay(e.target.value); }} /></label>
      <button className="skylit-trade-mode-btn" onClick={load} data-testid="solstice-replay-load"
        title="Load the selected recorded session; empty date uses the recorder's current day">
        {loading ? "Loading…" : `Replay ${ticker}`}
      </button>
      <button className="skylit-trade-mode-btn" onClick={compareLastTwo} data-testid="solstice-compare-btn"
        title="Session change window: wall-level change between the last two recorded snapshots (descriptive, not the spot/IV/time/OI counterfactual)">
        Compare last two
      </button>
      {snaps.length > 0 && (
        <>
          <button className="skylit-trade-mode-btn" onClick={togglePlay} data-testid="solstice-replay-play"
            title={playing ? "Pause recorded playback" : "Play recorded snapshots in order (stops at the last record; never arms live refresh)"}>
            {playing ? "Pause" : "Play"}
          </button>
          <input type="range" min={0} max={snaps.length - 1} step={1}
            value={scrubIndex >= 0 ? scrubIndex : 0}
            data-testid="solstice-replay-scrub" aria-label="Replay timeline scrubber"
            title="Scrub recorded snapshots (recorded time only)"
            onChange={(e) => {
              const s = snaps[Number(e.target.value)];
              if (s) openSnap(s.id);
            }} />
          <span data-testid="solstice-replay-range"
            title="Recorded range start · current · end">
            {String(snaps[0]?.asof || "").slice(11, 16)} · {String(snaps[scrubIndex >= 0 ? scrubIndex : 0]?.asof || "").slice(11, 16)} · {String(snaps[snaps.length - 1]?.asof || "").slice(11, 16)}
          </span>
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
      {manifest?.day && <span>Stored session {manifest.day} · {Array.isArray(manifest.gaps) ? `${manifest.gaps.length} declared gaps` : "gap coverage unknown"}</span>}
      {health?.capture && <span>Capture {health.capture.worker_state || "state unknown"}</span>}
      {refusal && <span role="alert">{refusal}</span>}
      {manifest?.error && <span role="alert">Replay unavailable · {manifest.error}</span>}
      {health?.error && <span>Recorder health unavailable</span>}
      {compare && !["ok", "history_unavailable"].includes(compare.status) && <span role="status" title={compare.detail || "Comparable identity, source, scope, formula, session and ordering are required"}>Comparison unavailable · {compare.reason || compare.error || compare.status || "COMPARISON_UNAVAILABLE"}</span>}
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

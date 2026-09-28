import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import { API } from "../config/api";
import SkylitHeatmapGrid from "./heatseeker/SkylitHeatmapGrid";
import { mapSurface } from "./heatseeker/shownMapStrikes";
import { wallPositionOf } from "../lib/solsticeSelection";
import { useReviewJournal } from "./triad/useReviewJournal";

/**
 * TrinityView — Triad 0DTE review desk (O4 rebuild).
 *
 * Consumes the versioned heatmap snapshot projection directly
 * (GET /api/heatmap/{ticker}: snapshotId, formula_version, walls, grids,
 * scenarios, quality). The old Public-chain mapper (client-side gex split
 * by sign, 200-contract truncation, hardcoded fallback expiry, vex: 0,
 * empty floors/ceilings) is gone: every number on screen is a backend
 * packet field, and anything missing renders as unavailable.
 *
 * Layout: compact SPY/QQQ/SPX context strip, one focused symbol, one
 * raw/adjusted pair on the same rail, selected-wall scenario card,
 * contract-review drawer, second-level review journal.
 */
const TRIAD = ["^SPX", "SPY", "QQQ"];
const HANDOFF_KEY = "solstice.triadHandoff";

// Adjusted bases available in the snapshot contract (metrics.grids).
// Window Δvolume×delta has no per-strike surface in the packet, so it is
// offered disabled with the reason rather than invented client-side.
const ADJUSTED_BASES = [
  { id: "delta", label: "Δ-weighted OI", units: "USD/1% move · dadgex_net_v1 — experimental weighting, not flow" },
  { id: "activity", label: "Session vol × Δ", units: "volume_gamma — session turnover, not positioning" },
  { id: "window", label: "Window Δvol", units: null },
];

function readHandoff() {
  try {
    const raw = sessionStorage.getItem(HANDOFF_KEY);
    if (!raw) return null;
    sessionStorage.removeItem(HANDOFF_KEY);
    const h = JSON.parse(raw);
    return h && typeof h === "object" ? h : null;
  } catch {
    return null;
  }
}

function wallForStrike(walls, strike) {
  const s = Number(strike);
  if (!Number.isFinite(s)) return null;
  return (walls || []).find((w) => s >= Number(w.low) && s <= Number(w.high)) || null;
}

function scenariosForWall(scenarios, wall, spot) {
  const list = (scenarios || []).filter((sc) => !wall || sc.wall_id === wall.wall_id);
  if (list.length || !wall) return list;
  // Compat fallback (same derivation as the Solstice drawer): position-based
  // two-sided watch. Never another wall's scenarios.
  const wpos = wallPositionOf(wall, spot);
  const side = wpos === "inside" ? "below" : wpos;
  return [
    { wall_id: wall.wall_id, wall_position: wpos,
      name: side === "below" ? "Bounce watch" : "Rejection watch", type: "reversal_watch",
      confirmation: `reclaim and hold ${side === "below" ? "above " + wall.low : "below " + wall.high}`,
      invalidation: `sustained acceptance ${side === "below" ? "below " + wall.low : "above " + wall.high}` },
    { wall_id: wall.wall_id, wall_position: wpos,
      name: side === "below" ? "Breakdown continuation" : "Breakout continuation", type: "continuation",
      confirmation: "acceptance beyond zone + follow-through/retest",
      invalidation: `reclaim and hold ${side === "below" ? "above " + wall.low : "below " + wall.high}` },
  ];
}

function TrinityView({ onFocusTicker, onTradeSelect }) {
  const [handoff] = useState(readHandoff);
  const [ticker, setTicker] = useState(handoff?.ticker || "SPY");
  const [symbolInput, setSymbolInput] = useState(handoff?.ticker || "SPY");
  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [wallId, setWallId] = useState(handoff?.wall_id || null);
  const [basis, setBasis] = useState("delta");
  const [board, setBoard] = useState([]);
  const [contract, setContract] = useState(null);
  const [contractLoading, setContractLoading] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const genRef = useRef(0);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  // Focused-symbol snapshot projection (the contract — no client math).
  useEffect(() => {
    const myGen = ++genRef.current;
    const ctrl = new AbortController();
    setLoading(true);
    setError(null);
    setPayload(null);
    setWallId(handoff?.wall_id || null);
    axios
      .get(`${API}/heatmap/${encodeURIComponent(ticker)}?mode=day&expiries=4`, {
        timeout: 45000, signal: ctrl.signal,
      })
      .then((r) => {
        if (!mountedRef.current || genRef.current !== myGen) return;
        setPayload(r.data);
        setLoading(false);
      })
      .catch((e) => {
        if (!mountedRef.current || genRef.current !== myGen) return;
        if (e?.name === "CanceledError" || e?.code === "ERR_CANCELED") return;
        setError(e?.response?.data?.detail || e.message || "fetch failed");
        setLoading(false);
      });
    return () => { ctrl.abort(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticker]);

  // Context strip: free leaderboard read (no scan, no budget spend).
  useEffect(() => {
    let cancelled = false;
    axios
      .get(`${API}/flowseeker/universe/leaderboard?limit=12`, { timeout: 15000 })
      .then((r) => { if (!cancelled) setBoard(r?.data?.leaderboard || []); })
      .catch(() => { /* strip degrades to focused-symbol only */ });
    return () => { cancelled = true; };
  }, []);

  const walls = useMemo(() => payload?.metrics?.walls || [], [payload]);
  const spot = payload?.spot ?? null;
  const selectedWall = useMemo(
    () => (walls || []).find((w) => w.wall_id === wallId) || null,
    [walls, wallId]
  );
  const rawSurface = useMemo(() => mapSurface(payload, "gex", "raw"), [payload]);
  const adjSurface = useMemo(() => mapSurface(payload, "gex", basis), [payload, basis]);
  const adjDef = ADJUSTED_BASES.find((b) => b.id === basis);
  const adjAvailable = basis !== "window" && adjSurface.available;
  const scenarios = useMemo(
    () => scenariosForWall(payload?.scenarios, selectedWall, spot),
    [payload, selectedWall, spot]
  );
  const quality = payload?.quality || null;

  const submitSymbol = useCallback(() => {
    const t = (symbolInput || "").trim().toUpperCase();
    if (!t || t === ticker) return;
    setTicker(t);
    setContract(null);
    setDrawerOpen(false);
    if (onFocusTicker) onFocusTicker(t);
  }, [symbolInput, ticker, onFocusTicker]);

  const selectWall = useCallback((id) => {
    setWallId(id);
    setContract(null);
  }, []);

  const onGridCell = useCallback((strike) => {
    const w = wallForStrike(walls, strike);
    if (w) {
      selectWall(w.wall_id);
    } else {
      selectWall(null);
    }
  }, [walls, selectWall]);

  // Contract review drawer: real detail route for the selected wall zone.
  // Uses the wall mid + first expiry column; rows carry bid/ask/quote state.
  const openContracts = useCallback(() => {
    const strike = selectedWall ? selectedWall.mid ?? selectedWall.low : null;
    const expiry = payload?.grid?.expiries?.[0] || payload?.expiries_used?.[0];
    if (strike == null || !expiry || !ticker) return;
    setDrawerOpen(true);
    setContractLoading(true);
    setContract(null);
    axios
      .get(`${API}/contract/${encodeURIComponent(ticker)}/${strike}/${encodeURIComponent(expiry)}`, { timeout: 20000 })
      .then((r) => setContract(r.data))
      .catch((e) => setContract({ error: e?.response?.data?.detail || e.message || "contract unavailable" }))
      .finally(() => setContractLoading(false));
  }, [selectedWall, payload, ticker]);

  const journal = useReviewJournal(ticker, payload?.snapshotId,
    `triad wall ${selectedWall?.wall_id || "?"} basis ${basis} mode live`);

  const isSPX = ticker === "^SPX" || ticker === "SPX";
  const spxMissing = isSPX && !loading && (!payload || !payload.strikes?.length);

  if (loading && !payload) {
    return (
      <div className="trinity-loading">
        <div className="trinity-loading-spinner" />
        <span>Loading Triad…</span>
      </div>
    );
  }
  if ((error || !payload) && !loading) {
    return (
      <div className="trinity-error" data-testid="triad-error">
        <span>⚠</span> {isSPX
          ? "SPX unavailable in this session (entitlement/coverage unknown). No substitution made — pick another symbol."
          : `Error: ${error || "no data"}`}
        <button onClick={() => setTicker("SPY")}>SPY</button>
      </div>
    );
  }

  return (
    <div className="trinity-layout" data-testid="trinity-view">
      <ContextStrip board={board} ticker={ticker} symbolInput={symbolInput}
        onSymbolInput={setSymbolInput} onSubmit={submitSymbol} />
      <div className="triad-pair" data-testid="triad-raw-adjusted">
        <div className="triad-pane" data-testid="triad-pane-raw">
          <div className="triad-pane-header" title="Raw structural GEX — gex_net_v1/gex_gross_v1, USD per 1% spot move">
            Raw GEX · USD/1% move · {payload?.formula_version || "gex.v2"}
          </div>
          <SkylitHeatmapGrid data={payload} spot={spot} ticker={ticker}
            viewMode="gex" metric="raw" onCellClick={(s) => onGridCell(s)} />
        </div>
        <div className="triad-pane" data-testid="triad-pane-adjusted">
          <div className="triad-pane-header" title={adjDef?.units || "No per-strike surface for this basis in the snapshot"}>
            Adjusted · {adjDef?.label || basis}{adjAvailable ? ` · ${adjDef.units}` : " · unavailable"}
          </div>
          {adjAvailable ? (
            <SkylitHeatmapGrid data={payload} spot={spot} ticker={ticker}
              viewMode="gex" metric={basis} onCellClick={(s) => onGridCell(s)} />
          ) : (
            <div className="triad-unavailable" data-testid="triad-adjusted-unavailable"
              title={basis === "window" ? "window_dadgex has no per-strike surface in the snapshot contract" : "adjusted surface missing from this snapshot"}>
              {basis === "window"
                ? "Window Δvol has no per-strike surface in this snapshot — not invented here."
                : "Adjusted surface unavailable in this snapshot — showing nothing rather than borrowing Raw."}
            </div>
          )}
        </div>
      </div>
      <div className="triad-basis-row">
        <span className="triad-basis-label">Adjusted basis:</span>
        {ADJUSTED_BASES.map((b) => {
          const dis = b.id === "window";
          return (
            <button key={b.id}
              className={`triad-basis-btn${basis === b.id ? " active" : ""}`}
              disabled={dis}
              title={dis ? "Window Δvol: no per-strike surface in the snapshot contract" : b.units}
              data-testid={`triad-basis-${b.id}`}
              onClick={() => setBasis(b.id)}>
              {b.label}
            </button>
          );
        })}
      </div>
      {spxMissing && (
        <div className="triad-capability" data-testid="triad-spx-capability">
          SPX unavailable in this session (entitlement/coverage unknown). No substitution made.
        </div>
      )}
      <WallBar walls={walls} wallId={selectedWall?.wall_id || null} onSelect={selectWall} />
      {selectedWall ? (
        <ScenarioCard wall={selectedWall} scenarios={scenarios} spot={spot}
          quality={quality} onContracts={openContracts} onTradeSelect={onTradeSelect} ticker={ticker} />
      ) : (
        <div className="triad-nowall" data-testid="triad-no-wall">
          No structural wall selected — pick a cell in either pane. An adjusted-only peak with no
          corresponding GEX wall will say so here rather than inheriting another wall's story.
        </div>
      )}
      {drawerOpen && (
        <ContractDrawer contract={contract} loading={contractLoading}
          wall={selectedWall} onClose={() => setDrawerOpen(false)} ticker={ticker} />
      )}
      <ReviewSection journal={journal} ticker={ticker} snapshotId={payload?.snapshotId} />
      <div className="triad-source" data-testid="triad-source">
        {payload?.snapshotId ? `snapshot ${payload.snapshotId}` : "no snapshot"}
        {payload?.asof ? ` · ${payload.asof}` : ""}
        {payload?.data_source ? ` · ${payload.data_source}` : ""}
        {quality?.state ? ` · quality ${quality.state}` : ""}
      </div>
    </div>
  );
}

function ContextStrip({ board, ticker, symbolInput, onSymbolInput, onSubmit }) {
  const byTicker = useMemo(() => {
    const m = {};
    for (const r of board || []) m[String(r.ticker || "").toUpperCase()] = r;
    return m;
  }, [board]);
  const observed = TRIAD.filter((t) => byTicker[t.replace("^", "")] || byTicker[t]);
  const dirs = observed.map((t) => (byTicker[t.replace("^", "")] || byTicker[t])?.direction).filter(Boolean);
  return (
    <div className="triad-context" data-testid="triad-context">
      {TRIAD.map((t) => {
        const r = byTicker[t.replace("^", "")] || byTicker[t];
        return (
          <div key={t} className="triad-context-cell" data-testid={`triad-context-${t.replace("^", "")}`}>
            <span className="triad-context-ticker">{t}</span>
            {r ? (
              <>
                <span className="triad-context-conv">{r.conviction ?? "—"}</span>
                <span className="triad-context-tier">{r.tier || ""}</span>
                <span className="triad-context-dir">{r.direction || ""}</span>
              </>
            ) : (
              <span className="triad-context-missing" title="Not in the latest leaderboard sweep — unobserved, not zero">unscanned</span>
            )}
          </div>
        );
      })}
      <div className="triad-context-focus">
        <input value={symbolInput} onChange={(e) => onSymbolInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") onSubmit(); }}
          data-testid="triad-symbol-input" aria-label="Focused symbol" placeholder="SYM" />
        <button onClick={onSubmit} data-testid="triad-symbol-go" title="Load this symbol's snapshot (its own data only)">Go</button>
      </div>
      <div className="triad-context-note" data-testid="triad-coverage-note"
        title="Coverage description only — never a position size">
        {observed.length}/3 observed{dirs.length ? ` · ${dirs.join(" / ")}` : ""}
      </div>
      {ticker && !TRIAD.includes(ticker) && (
        <div className="triad-context-focusname" data-testid="triad-focus-name">Focused: {ticker}</div>
      )}
    </div>
  );
}

function WallBar({ walls, wallId, onSelect }) {
  if (!walls || !walls.length) {
    return (
      <div className="triad-walls" data-testid="triad-walls-empty">
        No structural walls in this snapshot.
      </div>
    );
  }
  return (
    <div className="triad-walls" data-testid="triad-walls">
      {(walls || []).map((w) => (
        <button key={w.wall_id}
          className={`triad-wall-chip${w.wall_id === wallId ? " active" : ""}`}
          data-testid={`triad-wall-${w.wall_id}`}
          title={`zone ${w.low}–${w.high} · gross ${w.gross} · net ${w.net}`}
          onClick={() => onSelect(w.wall_id === wallId ? null : w.wall_id)}>
          {w.low}–{w.high}
        </button>
      ))}
    </div>
  );
}

function ScenarioCard({ wall, scenarios, spot, quality, onContracts, onTradeSelect, ticker }) {
  const [first, second] = scenarios || [];
  return (
    <div className="triad-scenario" data-testid="triad-scenario">
      <div className="triad-scenario-zone" data-testid="triad-scenario-zone">
        Wall {wall.wall_id} · zone {wall.low}–{wall.high}
        {spot != null && wall.mid != null ? ` · ${Math.abs(spot - wall.mid).toFixed(1)} from mid` : ""}
      </div>
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
      <WallPricePath ticker={ticker} wall={wall} spot={spot} />
      <button className="triad-contracts-btn" data-testid="triad-contracts-btn"
        title="Review contracts at this wall (identity, delta, spread, quote age)"
        onClick={onContracts}>
        Review contracts
      </button>
    </div>
  );
}

function WallPricePath({ ticker, wall, spot }) {
  const [frames, setFrames] = useState(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!ticker || !wall) return undefined;
    let cancelled = false;
    const ctrl = new AbortController();
    axios
      .get(`${API}/heatseeker/price-history/${encodeURIComponent(ticker)}`, {
        params: { days: 5 }, timeout: 30000, signal: ctrl.signal,
      })
      .then((r) => { if (!cancelled) setFrames(r?.data?.frames || []); })
      .catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; ctrl.abort(); };
  }, [ticker, wall?.wall_id]);
  const closes = useMemo(
    () => (frames || []).map((f) => Number(f.close)).filter((c) => Number.isFinite(c)),
    [frames]
  );
  if (frames === null && !failed) {
    return <div className="triad-price-loading">loading price path…</div>;
  }
  if (failed) {
    return <div className="triad-price-empty" data-testid="triad-price-empty">Price history unavailable for this symbol.</div>;
  }
  if (!closes.length) {
    return <div className="triad-price-empty" data-testid="triad-price-empty">No price candles for this period.</div>;
  }
  const W = 300, H = 120, PAD = 6;
  const lo = Math.min(...closes, Number(wall.low));
  const hi = Math.max(...closes, Number(wall.high));
  const span = hi - lo || 1;
  const X = (i) => PAD + (closes.length < 2 ? W / 2 : (i / (closes.length - 1)) * (W - 2 * PAD));
  const Y = (v) => H - PAD - ((Number(v) - lo) / span) * (H - 2 * PAD);
  const pts = closes.map((c, i) => `${X(i).toFixed(1)},${Y(c).toFixed(1)}`).join(" ");
  const zy1 = Y(Math.min(Number(wall.high), hi));
  const zy2 = Y(Math.max(Number(wall.low), lo));
  const spotY = spot != null && Number.isFinite(Number(spot)) ? Y(Number(spot)) : null;
  return (
    <div className="triad-price" data-testid="triad-price-path">
      <svg data-testid="triad-price-path-svg" viewBox={`0 0 ${W} ${H}`} width="100%" height="120"
        role="img" aria-label={`Recent closes with wall zone ${wall.low} to ${wall.high}`}>
        <rect data-testid="triad-price-zone" x={PAD} y={Math.min(zy1, zy2)}
          width={W - 2 * PAD} height={Math.abs(zy2 - zy1)}
          fill="rgba(251,191,36,0.12)" />
        <polyline points={pts} fill="none" stroke="#7dd3fc" strokeWidth="1.5" />
        {spotY != null && spotY >= 0 && spotY <= H && (
          <line x1={PAD} x2={W - PAD} y1={spotY} y2={spotY} stroke="#f472b6" strokeWidth="1" strokeDasharray="4 3" />
        )}
      </svg>
      <div className="triad-price-caption" data-testid="triad-price-caption">
        {closes.length} closes · zone shaded · VWAP unavailable (no verified source)
      </div>
    </div>
  );
}

function ContractDrawer({ contract, loading, wall, onClose, ticker }) {
  const rows = contract?.contracts || [];
  return (
    <div className="triad-drawer" data-testid="triad-contract-drawer" role="dialog" aria-label="Contract review">
      <div className="triad-drawer-header">
        <span>Contracts · {ticker} {wall ? `${wall.low}–${wall.high}` : ""}</span>
        <button onClick={onClose} data-testid="triad-drawer-close" aria-label="Close contract review">✕</button>
      </div>
      {loading && <div className="triad-drawer-loading">loading contracts…</div>}
      {!loading && contract?.error && (
        <div className="triad-drawer-error" data-testid="triad-contract-error">{contract.error}</div>
      )}
      {!loading && !contract?.error && (
        <table className="triad-contract-table">
          <thead><tr><th>Contract</th><th>Exp</th><th>Δ</th><th>Bid/Ask</th><th>Spread</th><th>IV</th><th>OI</th></tr></thead>
          <tbody>
            {rows.map((c, i) => {
              const spread = c.ask != null && c.bid != null ? (Number(c.ask) - Number(c.bid)) : null;
              return (
                <tr key={c.osi || i} data-testid="triad-contract-row">
                  <td>{c.osi || `${c.type || ""} ${c.strike ?? ""}`}</td>
                  <td>{c.expiry || ""}</td>
                  <td>{c.delta ?? "—"}</td>
                  <td>{c.bid ?? "—"} / {c.ask ?? "—"}</td>
                  <td>{spread == null || Number.isNaN(spread) ? "—" : spread.toFixed(2)}</td>
                  <td>{c.iv ?? "—"}</td>
                  <td>{c.open_interest ?? c.oi ?? "—"}</td>
                </tr>
              );
            })}
            {!rows.length && (
              <tr><td colSpan={7}>No contracts returned for this zone.</td></tr>
            )}
          </tbody>
        </table>
      )}
    </div>
  );
}

function ReviewSection({ journal, ticker, snapshotId }) {
  const { reviewState, reviewDec, reviewQueue, reviewReason, setReviewReason,
    reviewSaving, reviewLoading, saveReview } = journal;
  return (
    <div className="triad-review" data-testid="triad-review">
      <span className="triad-review-label">Review</span>
      {reviewLoading && <span data-testid="triad-review-loading">loading review…</span>}
      {!reviewLoading && reviewState !== null && (
        <span data-testid="triad-review-state">Decision: {reviewState}</span>
      )}
      {!reviewLoading && reviewState === null && snapshotId && (
        <span data-testid="triad-review-pending">No review yet</span>
      )}
      {!reviewLoading && reviewDec && (
        <div data-testid="triad-review-save">
          {["reviewed", "waiting", "skipped"].map((s) => (
            <button key={s} data-testid={`triad-review-save-${s}`} disabled={reviewSaving}
              title={`Mark this decision ${s} (frozen snapshot context)`}
              onClick={() => saveReview(s)}>{s}</button>
          ))}
          <select data-testid="triad-review-reason" value={reviewReason}
            onChange={(e) => setReviewReason(e.target.value)} title="Reason recorded with the review">
            <option value="">reason…</option>
            {["CONFIRMED_SETUP", "NEEDS_MORE_EVIDENCE", "STALE_DATA", "WRONG_WALL", "TIME_EXPIRED"].map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
        </div>
      )}
      {reviewQueue.length > 0 && (
        <div data-testid="triad-review-queue" title="Unreviewed decisions, newest first (max 5)">
          <span>Next to review:</span>
          {reviewQueue.map((d) => (
            <span key={d.decision_id} className="triad-review-chip" data-testid={`triad-review-open-${d.decision_id}`}>
              {d.scenario || d.side || d.decision_id}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export default TrinityView;

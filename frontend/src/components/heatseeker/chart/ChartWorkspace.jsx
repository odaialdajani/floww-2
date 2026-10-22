import React, { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import PriceNodeHistory from '../PriceNodeHistory';
import ChartPane from './ChartPane';
import AtlasChart from './AtlasChart';
import PaneLayouts, { LAYOUT_PRESETS, layoutById } from './PaneLayouts';
import { createPanes, panesReducer } from './chartReducer';
import { createLayout, migrate, sanitizeImport, serialize } from './persistence/layoutSchema';
import { listLocal, loadLocal, saveLocal, scheduleAutosave } from './persistence/layoutStore';
import { DEFAULT_SHORTCUTS, LONG_PRESS_MS, actionFor, keyOf, nextFitMode, rebind, watermark } from './ChartShortcuts';
import { clipboardState, composeExportSvg, exportPlan } from './ChartExport';
import { createReplayState, replayStep } from './replay/replayReducer';
import FlowPane, { bucketHash } from './indicators/FlowPane';
import { initialBalance, nakedLevels, poc, tickRows, valueArea } from './indicators/ProfilePrimitives';
import { levelLabel, topLevels } from './indicators/DarkPoolLevels';
import { candleDelta, sessionCvd } from './indicators/Footprint';
import { bindContext } from './context/chartContext';
import { flowWindowKeyFor } from './indicators/FlowPane';
import ChartDocks from './ChartDocks';
import './ChartWorkspace.css';
// B06 reversible single-pane workspace: controlled open + incumbent fallback.
// OFF (default) renders the exact incumbent PriceNodeHistory with EVERY caller
// prop passed through — toolbarActions, forcedScope, open/primary, contract
// premium, record-nodes, cvd/exposure lines. No existing control is removed.
// ON wraps the SAME incumbent inside a pane and surfaces its data-quality
// contract (source time, coverage, partial bars, capability reason, retry) via
// the PriceNodeHistory lifecycle, plus the workspace notice/retry and the
// opt-in Atlas overlay composed BESIDE the incumbent (never replacing it).
// B30 Atlas toggle stays default-off so existing screens never change unless
// the user flips it.
// B11: the flag-on branch adds the mounted pane manager — real layout presets
// (single/split/three), focusable panes each rendering a real chart, atomic
// evidence invalidation on layout change, and phone-stacked grids. The
// FOCUSED pane always carries the full incumbent prop set; extra panes are
// real per-instrument chart instances with their own lifecycles.
// B12: the composition (preset + pane symbols + focus) persists durably in
// versioned localStorage — it survives real reload/reopen — with debounced
// autosave, and the Layouts panel mounts save / cycle / export / import.
// Exports carry layout identity only: no secrets, no positions (the
// serializer refuses them); imports are sanitized (proto/scripts/unknown
// tools refused) and migrate corrupt payloads to a valid layout.
// B27: accessible usability is MOUNTED, not helper stubs — a live keyboard
// map (typing fields never fire shortcuts; Escape closes overlays; keys are
// rebindable with typed visible refusals), touch long-press opens the
// layouts sheet, a Replay control sits above the chips, two auto-fit modes
// persist with the layout, the source/proxy/replay watermark renders live,
// image export composes the real pane composition into SVG, and clipboard
// denial is an explicit visible state. The phone layouts panel is a bottom
// sheet that stays clear of the keyboard (dvh cap + safe-area padding).
export function isChartWorkspaceEnabled() {
  return typeof window !== 'undefined' && window.__FLOWW_CHART_WORKSPACE__ === true;
}

const WORKSPACE_LAYOUT_KEY = 'workspace-current';

export default function ChartWorkspace({
  ticker, useNew = false, open = true, primary = false, toolbarActions = null,
  forcedScope = null, onRecordNodes = null, showAtlas = true, exposureLine = null,
  darkLevels = null, flowBars = null, cvdLine = null,
  notice = null, onRetry = null, frames = null, nodes = [], bars = [], flow = null, atlasDarkLevels = [],
  flowTrades = null, onFlowBucket = null,
  profileTrades = null, darkPoolPrints = null, classifiedBars = null, priorLevels = null,
  ibEnvelope = null, nakedEnvelope = null, flowEnvelope = null,
  onChartContext = null,
  docksMaps = {}, docksSidecar = null,
}) {
  const [atlas, setAtlas] = useState(false);
  const [quality, setQuality] = useState(null);
  const [envelopes, setEnvelopes] = useState(null);
  const [layoutId, setLayoutId] = useState('single');
  const [panes, dispatch] = useReducer(panesReducer, undefined, () => createPanes(1, ticker));
  const [layoutNote, setLayoutNote] = useState('');
  const [layoutsOpen, setLayoutsOpen] = useState(false);
  const [shortcuts, setShortcuts] = useState(DEFAULT_SHORTCUTS);
  const [rebindAction, setRebindAction] = useState(null);
  const [fitMode, setFitMode] = useState('fit-visible');
  const [replaying, setReplaying] = useState(false);
  const [exportNote, setExportNote] = useState('');
  // B15 replay algebra consumer: the focused pane's replay reports flow
  // through replayReducer — the cursor, the partial/completed bar, extrema
  // swept at the cursor and the live/replay cache split. Replay-derived
  // events are admitted ONLY to the replay cache; the live cache never
  // receives them (routeEvent enforces the split inside replayReducer).
  const [replay, replayDispatch] = useReducer(replayStep, undefined, () => createReplayState());
  // R21-06: the binding ties a report to the exact pane instance that
  // produced it (pane id + symbol). Late reports from a pane that is no
  // longer focused are DROPPED; layout changes revoke every prior binding
  // (panes are recreated); the live identity never copies the stale report
  // it is validating.
  const [replayBinding, setReplayBinding] = useState(null);
  const panesRef = useRef(panes); panesRef.current = panes;
  const lastLayoutForBinding = useRef(null);
  // Stable identity: the pane's report effect depends on this callback, so a
  // new function per render would re-fire the effect forever. Dispatches and
  // refs only — the memo never goes stale.
  const handlePaneReplayState = useCallback((report) => {
    const focused = panesRef.current.find(p => p.focused) || panesRef.current[0];
    // Late reports from a pane that lost focus are refused; only the LIVE
    // focused pane's reports bind. (The pane carries its own source id, so
    // this callback keeps ONE stable identity — a per-render closure here
    // would re-fire the pane's report effect forever.)
    if (!report) { setReplayBinding(null); return; }
    if (!focused || report.source !== focused.id) return;
    setReplayBinding({ paneId: focused.id, paneSymbol: focused.symbol, report });
    replayDispatch({ type: 'seek', cursor: report.cursor });
    for (const event of report.delta || []) replayDispatch({ type: 'admit', event });
  }, []);
  const restored = useRef(false);
  const longPressTimer = useRef(null);
  const lastContextEmit = useRef(null);
  // B24 focused-chart context: bind the FOCUSED pane's real identity (symbol,
  // saved-view scope, replay cursor, pane generation) through the mirror of
  // the server's chart_context contract. The ask gate resolves this
  // descriptor against the LIVE pane state — stale generations, scope changes
  // and removed panes refuse; the server stays the resolver of facts.
  const contextPane = panes.find(p => p.focused) || panes[0];
  // R21-06: validity is judged against the LIVE pane identity — a binding
  // from a pane that lost focus, changed symbol or was removed is revoked
  // atomically, before any newer report can arrive.
  if (lastLayoutForBinding.current !== layoutId) {
    lastLayoutForBinding.current = layoutId;
    if (replayBinding) setReplayBinding(null); // panes recreated: all prior reports stale
  }
  const bindingPane = replayBinding && contextPane
    && replayBinding.paneId === contextPane.id && replayBinding.paneSymbol === contextPane.symbol
    ? replayBinding : null;
  const liveReport = bindingPane ? bindingPane.report : null;
  // Binding always runs through the mirror: an empty saved-view scope or a
  // missing pane identity is REFUSED with the contract's reason, never
  // silently blank. The ask gate refuses on the same reason.
  const chartDescriptor = liveReport
    ? bindContext({ focus: contextPane.symbol, query: 'focused-chart', scope: liveReport.scope, cursor: liveReport.cursor, generation: liveReport.generation })
    : { status: 'refused', reason: replayBinding ? 'pane changed' : 'no focused pane report' };
  const chartCurrent = liveReport
    ? { generation: liveReport.generation, scope: liveReport.scope, pane_removed: false }
    : { generation: null, scope: null, pane_removed: !contextPane };
  const everBound = useRef(false);
  useEffect(() => {
    if (!onChartContext) return undefined;
    // Emit the bound identity and every subsequent REVOCATION after it; the
    // pre-report state stays silent so a fresh mount shows the legacy gate.
    if (chartDescriptor.status !== 'bound' && !everBound.current) return undefined;
    if (chartDescriptor.status === 'bound') everBound.current = true;
    const key = JSON.stringify([chartDescriptor, chartCurrent]);
    if (lastContextEmit.current === key) return undefined;
    lastContextEmit.current = key;
    onChartContext({ descriptor: chartDescriptor, current: chartCurrent });
    return undefined;
  }, [chartDescriptor, chartCurrent, onChartContext]); // eslint-disable-line react-hooks/exhaustive-deps
  const history = { ticker, open, primary, toolbarActions, forcedScope, onRecordNodes, showAtlas, exposureLine, darkLevels, flowBars, cvdLine, fitMode };

  // R21-03/04 supply wiring: the focused pane's own price-history fetch
  // publishes its recorded admission envelopes through onEnvelopes. An
  // explicit caller prop still wins (mount harness + host binding
  // contracts); with neither source present the legacy local algebra runs
  // exactly as committed — callers that never ask envelopes are byte-stable.
  const recordedEnvelopes = envelopes && typeof envelopes === 'object' ? envelopes : null;
  const ibSource = ibEnvelope ?? (recordedEnvelopes ? recordedEnvelopes.initial_balance : null);
  const nakedSource = nakedEnvelope ?? (recordedEnvelopes ? recordedEnvelopes.naked : null);
  const flowSource = flowEnvelope ?? (recordedEnvelopes ? recordedEnvelopes.flow : null);

  const applyPersisted = (data) => {
    if (!data || typeof data !== 'object') return false;
    const next = LAYOUT_PRESETS.some(p => p.id === data.layoutId) ? data.layoutId : 'single';
    setLayoutId(next);
    dispatch({ type: 'layout', layout: next, symbol: ticker });
    if (Array.isArray(data.symbols)) dispatch({ type: 'symbols', symbols: data.symbols });
    const focusedIdx = Number.isInteger(data.focusedIndex) && data.focusedIndex >= 0 && data.focusedIndex < 3 ? data.focusedIndex : 0;
    dispatch({ type: 'focus', id: 'pane-' + focusedIdx });
    if (data.fitMode === 'fit-visible' || data.fitMode === 'fit-all') setFitMode(data.fitMode);
    return true;
  };

  // B12 reopen: restore the durable composition once, before autosave can
  // overwrite it with the default single-pane state.
  useEffect(() => {
    if (restored.current) return undefined;
    restored.current = true;
    const raw = loadLocal(WORKSPACE_LAYOUT_KEY);
    if (raw !== null) {
      const { layout } = migrate(raw);
      applyPersisted(layout);
    }
    return undefined;
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // B12 debounced autosave: the composition persists on every change.
  useEffect(() => {
    if (!restored.current) return undefined;
    const focusedIdx = Math.max(0, panes.findIndex(p => p.focused));
    scheduleAutosave(WORKSPACE_LAYOUT_KEY, createLayout({
      layoutId,
      symbols: panes.map(p => p.symbol),
      focusedIndex: focusedIdx,
      fitMode,
    }));
    return undefined;
  }, [layoutId, panes, fitMode]);

  // B27 mounted keyboard map: typing fields never fire shortcuts (actionFor
  // guards), a pending rebind captures the next key with typed refusals,
  // Escape closes overlays. Handlers read the latest state via a ref so the
  // listener stays mounted once.
  const keyboardRef = useRef({});
  keyboardRef.current = { shortcuts, rebindAction, atlas, layoutsOpen, replaying };
  useEffect(() => {
    const onKeyDown = (event) => {
      const k = keyboardRef.current;
      if (k.rebindAction) {
        event.preventDefault();
        try {
          setShortcuts(rebind(k.shortcuts, k.rebindAction, keyOf(event)));
          setLayoutNote('Rebound ' + k.rebindAction + ' to ' + keyOf(event) + '.');
        } catch (error) {
          setLayoutNote('Rebind refused: ' + (error && error.message) + '.');
        }
        setRebindAction(null);
        return;
      }
      const action = actionFor(k.shortcuts, event);
      if (!action) return;
      if (action === 'escape') {
        event.preventDefault();
        // Close the topmost overlay first: the layouts sheet (modal-ish,
        // bottom-sheet on phone) before Atlas before the replay banner.
        if (k.layoutsOpen) setLayoutsOpen(false);
        else if (k.atlas) setAtlas(false);
        else if (k.replaying) setReplaying(false);
        return;
      }
      event.preventDefault();
      if (action === 'atlas') setAtlas(v => !v);
      else if (action === 'layouts') setLayoutsOpen(v => !v);
      else if (action === 'replay') setReplaying(v => !v);
      else if (action === 'fitMode') setFitMode(nextFitMode);
      else if (action === 'cycleLayout') {
        const names = listLocal().filter(n => n !== WORKSPACE_LAYOUT_KEY);
        if (!names.length) { setLayoutNote('No saved layouts to cycle.'); return; }
        const raw = loadLocal(names[0]);
        if (raw !== null) { const { layout } = migrate(raw); if (applyPersisted(layout)) setLayoutNote('Loaded ' + names[0] + '.'); }
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // B27 long-press (touch only): holding the pane area opens the layouts
  // sheet; a short tap cancels and never opens it.
  const startLongPress = (event) => {
    // Real browsers always stamp pointerType ('mouse'/'touch'/'pen'); test
    // environments without PointerEvent leave it unset — treat those as
    // touch-capable while explicit mouse/pen presses never long-press.
    if (event.pointerType && event.pointerType !== 'touch') return;
    if (longPressTimer.current) clearTimeout(longPressTimer.current);
    longPressTimer.current = setTimeout(() => {
      longPressTimer.current = null;
      setLayoutsOpen(true);
      setLayoutNote('Long-press: layouts opened.');
    }, LONG_PRESS_MS);
  };
  const cancelLongPress = () => {
    if (longPressTimer.current) { clearTimeout(longPressTimer.current); longPressTimer.current = null; }
  };
  useEffect(() => () => cancelLongPress(), []);

  if (!useNew) {
    return <PriceNodeHistory {...history} />;
  }
  const focusedPane = panes.find((p) => p.focused) || panes[0];
  const preset = layoutById(layoutId);
  const focusedIdx = Math.max(0, panes.findIndex(p => p.focused));
  const watermarkText = watermark({
    source: quality?.sourceTime ? 'saved-observations' : null,
    proxy: layoutNote.startsWith('Layout imported.') ? 'local-import' : null,
    replay: replaying,
  });

  const exportImage = async () => {
    const svg = composeExportSvg({ layoutId, panes, fitMode, watermarkText, quality, plan: exportPlan() });
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(svg);
        setExportNote(clipboardState(null) === 'copied' ? 'Export image copied.' : '');
      } else {
        setExportNote('Export denied — clipboard unavailable.');
      }
    } catch {
      setExportNote('Export denied — clipboard refused.');
    }
  };

  const exportLayoutIdentity = async () => {
    const text = serialize(createLayout({ layoutId, symbols: panes.map(p => p.symbol), focusedIndex: focusedIdx, fitMode }));
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
        setLayoutNote('Layout copied — layout identity only, no secrets or positions.');
      } else {
        setLayoutNote('Clipboard unavailable — layout not exported.');
      }
    } catch {
      setLayoutNote('Copy denied — layout not exported.');
    }
  };

  const importLayout = (event) => {
    const file = event.target.files && event.target.files[0];
    if (!file) { setLayoutNote('No layout file chosen.'); return; }
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const parsed = JSON.parse(String(reader.result));
        const clean = sanitizeImport(parsed);
        const { layout } = migrate(clean);
        if (applyPersisted(layout)) setLayoutNote('Layout imported.');
        else setLayoutNote('Layout file did not contain a readable composition.');
      } catch (error) {
        setLayoutNote(error && /proto|scripts|tools|bad-import/.test(String(error.message)) ? 'Layout refused: ' + error.message : 'Layout file could not be read.');
      }
    };
    reader.onerror = () => setLayoutNote('Layout file could not be read.');
    reader.readAsText(file);
  };

  const saveNamedLayout = () => {
    const name = 'layout-' + (listLocal().length + 1);
    try {
      saveLocal(name, createLayout({ layoutId, symbols: panes.map(p => p.symbol), focusedIndex: focusedIdx, fitMode }));
      setLayoutNote('Saved ' + name + '.');
    } catch (error) {
      setLayoutNote('Save refused: ' + (error && error.message) + '.');
    }
  };

  const cycleLayout = () => {
    const names = listLocal().filter(n => n !== WORKSPACE_LAYOUT_KEY);
    if (!names.length) { setLayoutNote('No saved layouts to cycle.'); return; }
    const raw = loadLocal(names[0]);
    if (raw === null) { setLayoutNote('Saved layout could not be read.'); return; }
    const { layout } = migrate(raw);
    if (applyPersisted(layout)) setLayoutNote('Loaded ' + names[0] + '.');
  };

  return (
    <div data-testid="chart-workspace" data-ticker={ticker}>
      <ChartPane symbol={ticker} interval="incumbent" status={quality?.status ?? 'loading'}>
        {/* B27 Replay control sits ABOVE the chips row on every viewport,
            with a touch-sized target and a visible replay state. */}
        <button type="button" data-testid="replay-touch" className="touch-replay" aria-pressed={replaying}
          onClick={() => setReplaying(v => !v)}>
          {replaying ? 'Pause replay' : 'Replay'}
        </button>
        {replaying && <p className="replay-banner" data-testid="replay-banner">Replay active — recorded session view.</p>}
        {/* B20 filtered premium flow at the replay cursor's bucket: the pane
            renders the FOCUSED bar's published trades (classified sides only,
            multi-leg tickets grouped economically). Totals and drilldown share
            one bar/window/filter identity, so they can only agree when they
            describe the same bucket. No published trades -> explicit unknown
            — aggregates are never inflated into invented trades. */}
        {liveReport && (() => {
          // R21-03 caller binding: the bucket identity keys on the OWNING
          // chart resolution (the pane's reported bar seconds) — the legacy
          // '1m' key stays only when the report carries no resolution.
          const windowKey = flowWindowKeyFor(liveReport.barSeconds) || '1m';
          return (
            <FlowPane
              trades={flowTrades}
              envelope={flowSource && typeof flowSource === 'object' ? flowSource : null}
              barId={liveReport.cursor}
              windowKey={windowKey}
              filters={{}}
              cursorHash={bucketHash(liveReport.cursor, windowKey, {})}
              onBucketClick={onFlowBucket ? (payload) => onFlowBucket(payload) : null}
            />
          );
        })()}
        {/* B23 profiles/TPO/session reads at the replay cursor: initial
            balance comes from the REAL visible bars (a labeled bar-resolution
            approximation); POC/value-area need EXACT classified trade prices
            (tick-binned, never bar-derived); CVD needs classified buy/sell
            sizes — candle direction is never a proxy; dark-pool levels need
            exact single prints — aggregates are refused. Every unavailable
            state is explicit, with its reason. */}
        {liveReport && (() => {
          const bars = liveReport.visible || [];
          // R21-04 caller binding: a server admission envelope (admit_initial_balance /
          // naked_levels_claim) overrides the local algebra — its refusal code or
          // coverage-honest bounds are the truth, never re-derived locally.
          const ibServer = ibSource && typeof ibSource === 'object' ? ibSource : null;
          const nakedServer = nakedSource && typeof nakedSource === 'object' ? nakedSource : null;
          const ib = ibServer ? null : initialBalance(bars, { periods: 2, cursor: liveReport.cursor });
          const tick = tickRows(profileTrades, 0.5);
          const rows = tick.status === 'ok' ? tick.rows : null;
          const pocRow = rows ? poc(rows) : null;
          const va = rows ? valueArea(rows, 0.7) : { status: 'unavailable', reason: tick.reason || 'no classified trade prices' };
          const cvd = classifiedBars ? sessionCvd(classifiedBars) : candleDelta();
          const dark = darkPoolPrints ? topLevels(darkPoolPrints, { topN: 3 }) : [];
          const naked = priorLevels ? nakedLevels(priorLevels, bars, { cursor: liveReport.cursor }) : [];
          const fmt = n => (Number.isFinite(n) ? `${Math.round(n * 100) / 100}` : 'unknown');
          return (
            <div className="profiles-panel" data-testid="profiles-panel"
              data-ib-status={ibServer ? ibServer.status : ib.status}
              data-ib-periods={(ibServer ? ibServer.status === 'available' : ib.status === 'ok') ? String(ibServer ? ibServer.coverage.expected_total : ib.periods) : '0'}
              data-va-status={va.status} data-cvd-status={cvd.status} data-dark-count={String(dark.length)}>
              <span data-testid="profile-ib">{ibServer
                ? (ibServer.status === 'available'
                    ? `Initial balance ${fmt(ibServer.bounds.low)}–${fmt(ibServer.bounds.high)} · ${ibServer.coverage.covered} of ${ibServer.coverage.expected_total} opening bars${ibServer.coverage.complete ? ' complete' : ' incomplete'} · ${ibServer.approximation} · ${ibServer.certification.basis}`
                    : `Initial balance ${ibServer.status} — ${ibServer.reason || 'unavailable'}`)
                : `Initial balance ${ib.status === 'ok'
                  ? `${fmt(ib.low)}–${fmt(ib.high)} over ${ib.periods} bars · ${ib.approximation}`
                  : ib.reason}`}</span>
              <span data-testid="profile-poc">{pocRow ? `POC ${fmt(pocRow.price)} · ${pocRow.volume}` : 'POC unavailable — no classified trade prices'}</span>
              <span data-testid="profile-va">{va.status === 'ok'
                ? `Value area ${fmt(va.low)}–${fmt(va.high)} · ${Math.round((va.attained || 0) * 100)}% attained (70% target)`
                : `Value area unavailable — ${va.reason}`}</span>
              <span data-testid="profile-cvd">{cvd.status === 'ok'
                ? `Session CVD ${cvd.rows.map(r => (r.delta >= 0 ? '+' : '') + Math.round(r.delta)).join(' ') || 'zero'} · last ${Math.round(cvd.rows[cvd.rows.length - 1].close)}`
                : `CVD unavailable — ${cvd.reason}`}</span>
              <span data-testid="profile-dark">{dark.length
                ? dark.map(levelLabel).join(' | ')
                : 'no dark-pool prints published — aggregates are never shown as single prints'}</span>
              {nakedServer ? <span data-testid="profile-naked">{nakedServer.status === 'available'
                ? `${(nakedServer.levels || []).filter(l => l && l.naked).length} naked level(s) beyond the cursor · server-admitted`
                : `Naked levels ${nakedServer.status} — ${nakedServer.reason || 'unavailable'}`}</span>
                : naked.length > 0 && <span data-testid="profile-naked">{naked.filter(l => l.naked).length} naked level(s) beyond the cursor</span>}
            </div>
          );
        })()}
        {/* B14 focused-pane sidecar dock (recovery carry): the FOCUSED
            pane's symbol follows the explicit sidecar policy
            (ok/stale/missing/removed/unavailable); map entries come from the
            consumer's existing map state and the sidecar content is the
            consumer's existing component — a frame, never another dashboard.
            Fetch subscriptions capped at MAX_SUBSCRIPTIONS with a census. */}
        <ChartDocks focusedSymbol={focusedPane.symbol} maps={docksMaps}
          subscriptionSymbols={panes.map(p => p.symbol)} renderSidecar={docksSidecar} />
        <div className="chart-context-strip" data-testid="chart-context"
          data-status={chartDescriptor ? chartDescriptor.status : 'unbound'}>
          Focused chart context {chartDescriptor && chartDescriptor.status === 'bound'
            ? `bound · ${chartDescriptor.focus} · scope ${chartDescriptor.scope || 'none'} · cursor ${chartDescriptor.cursor}`
            : `unavailable — ${chartDescriptor && chartDescriptor.reason ? chartDescriptor.reason : 'no focused pane report'}`}
        </div>
        {/* B15 mounted replay readout: the focused pane's real frames flow
            through the replay algebra — cursor, partial/completed bar, extrema
            swept strictly at-or-before the cursor, newest known-at, and the
            live/replay cache split. Replay events never enter live caches. */}
        {liveReport && (
          <div className="replay-readout" data-testid="replay-readout"
            data-cursor={liveReport.cursor}
            data-bar-state={liveReport.bar && liveReport.bar.complete ? 'complete' : 'partial'}
            data-live-count={Object.values(replay.caches.live || {}).reduce((n, m) => n + Object.keys(m || {}).length, 0)}
            data-replay-count={Object.values(replay.caches.replay || {}).reduce((n, m) => n + Object.keys(m || {}).length, 0)}>
            <span>Cursor {liveReport.cursorTime} · {liveReport.visibleBars}/{liveReport.totalBars} bars</span>
            <span>Bar {liveReport.bar && liveReport.bar.complete ? 'complete' : 'partial'} · open {liveReport.bar ? liveReport.bar.open : '—'} close {liveReport.bar ? liveReport.bar.close : '—'}</span>
            <span>Sweep high {liveReport.extrema.status === 'ok' ? liveReport.extrema.high : 'unknown'} · low {liveReport.extrema.status === 'ok' ? liveReport.extrema.low : 'unknown'} · {liveReport.extrema.status === 'ok' ? liveReport.extrema.count + ' bars' : liveReport.extrema.reason}</span>
            <span>Known-at {liveReport.snapshotKnownAt ?? 'unknown'}</span>
            <span>live {Object.values(replay.caches.live || {}).reduce((n, m) => n + Object.keys(m || {}).length, 0)} · replay {Object.values(replay.caches.replay || {}).reduce((n, m) => n + Object.keys(m || {}).length, 0)} · replay events never enter live caches</span>
          </div>
        )}
        <button type="button" data-testid="atlas-toggle" aria-pressed={atlas} onClick={() => setAtlas((v) => !v)}>
          {atlas ? 'Hide Atlas overlay' : 'Show Atlas overlay'}
        </button>
        {/* B11 mounted pane manager: layout presets drive the visible pane
            count; every layout change invalidates pane evidence atomically
            (generations advance together, late results are rejected). */}
        <div className="pane-layout-picker" role="group" aria-label="Chart pane layout">
          {LAYOUT_PRESETS.map(p => (
            <button
              key={p.id}
              type="button"
              data-testid={'layout-' + p.id}
              aria-pressed={layoutId === p.id}
              onClick={() => { setLayoutId(p.id); dispatch({ type: 'layout', layout: p.id, symbol: ticker }); }}
            >
              {p.label}
            </button>
          ))}
          {/* B27 two auto-fit modes, persisted with the composition. */}
          <button type="button" data-testid="fit-mode" aria-label="Auto-fit mode"
            onClick={() => setFitMode(nextFitMode)}>
            Auto-fit: {fitMode}
          </button>
        </div>
        <div onPointerDown={startLongPress} onPointerUp={cancelLongPress} onPointerLeave={cancelLongPress} onPointerCancel={cancelLongPress}>
          <PaneLayouts
            layout={layoutId}
            panes={panes}
            onFocus={(id) => dispatch({ type: 'focus', id })}
            renderPane={(pane) => (pane.id === focusedPane.id
              ? <PriceNodeHistory {...history}
                  ticker={pane.symbol}
                  forcedScope={pane.symbol === ticker ? forcedScope : null}
                  exposureLine={pane.symbol === ticker ? exposureLine : null}
                  darkLevels={pane.symbol === ticker ? darkLevels : null}
                  flowBars={pane.symbol === ticker ? flowBars : null}
                  cvdLine={pane.symbol === ticker ? cvdLine : null}
                  onQuality={setQuality} onEnvelopes={setEnvelopes} onReplayState={handlePaneReplayState} replaySourceId={pane.id}
                  replayEpoch={layoutId + ':' + pane.generation} />
              : <PriceNodeHistory ticker={pane.symbol} open={open} primary={false} showAtlas={showAtlas} fitMode={fitMode} />)}
          />
        </div>
        {/* B27 source/proxy/replay watermark: rendered live and composed into
            every export. */}
        <span className="chart-watermark" data-testid="chart-watermark">{watermarkText || 'source:saved-observations'}</span>
        {/* B12 mounted layouts UX: durable save, cycle, sanitized import and
            secret-free export for the live composition. B27: a phone bottom
            sheet that stays clear of the keyboard, with the rebindable
            keyboard map and composite image export inside. */}
        <details className="workspace-layouts" data-testid="layouts-panel" open={layoutsOpen}
          onToggle={(event) => setLayoutsOpen(event.currentTarget.open)}>
          <summary role="button">Layouts</summary>
          <div className="workspace-layouts-row">
            <button type="button" data-testid="layout-save" onClick={saveNamedLayout}>Save layout</button>
            <button type="button" data-testid="layout-cycle" onClick={cycleLayout}>Cycle saved layout</button>
            <button type="button" data-testid="layout-export" onClick={exportLayoutIdentity}>Export layout</button>
            <button type="button" data-testid="export-image" onClick={exportImage}>Export image</button>
            <label className="workspace-layouts-import">Import layout
              <input type="file" data-testid="layout-import" accept="application/json,.json" onChange={importLayout} />
            </label>
          </div>
          {/* B27 rebindable keyboard map with visible refusals. */}
          <div className="workspace-shortcuts" data-testid="shortcuts-panel">
            <strong>Keyboard shortcuts</strong>
            {Object.entries(shortcuts).map(([action, key]) => (
              <span key={action} className="shortcut-row">
                <span>{action}: <kbd data-testid={'key-' + action}>{key}</kbd></span>
                <button type="button" data-testid={'rebind-' + action} aria-pressed={rebindAction === action}
                  onClick={() => { setRebindAction(action); setLayoutNote('Press a new key for ' + action + '.'); }}>
                  {rebindAction === action ? 'Press a key…' : 'Rebind'}
                </button>
              </span>
            ))}
          </div>
          {exportNote && <span role="status" data-testid="export-status">{exportNote}</span>}
          {layoutNote && <span role="status" data-testid="layout-status">{layoutNote}</span>}
        </details>
        {atlas
          ? <AtlasChart ticker={ticker} frames={frames} nodes={nodes} bars={bars} flow={flow} darkLevels={atlasDarkLevels} enabled />
          : null}
        {quality && (
          <div data-testid="workspace-quality" data-status={quality.status}>
            <span>Latest reading {quality.sourceTime ?? 'time unknown'}</span>
            <span>{quality.coverage}</span>
            {quality.partialBars && <span>{quality.partialBars}</span>}
            {quality.capability && <span>Saved node history {quality.capability}</span>}
            <span>{quality.retry}</span>
          </div>
        )}
        {notice && <p data-testid="workspace-notice">{notice}</p>}
        {onRetry && <button type="button" onClick={onRetry}>Retry</button>}
        <span className="pane-layout-note" data-testid="pane-count">{preset.panes} {preset.panes === 1 ? 'pane' : 'panes'} · focused {focusedPane.symbol}</span>
      </ChartPane>
    </div>
  );
}

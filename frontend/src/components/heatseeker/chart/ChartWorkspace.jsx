import React, { useEffect, useReducer, useRef, useState } from 'react';
import PriceNodeHistory from '../PriceNodeHistory';
import ChartPane from './ChartPane';
import AtlasChart from './AtlasChart';
import PaneLayouts, { LAYOUT_PRESETS, layoutById } from './PaneLayouts';
import { createPanes, panesReducer } from './chartReducer';
import { createLayout, migrate, sanitizeImport, serialize } from './persistence/layoutSchema';
import { listLocal, loadLocal, saveLocal, scheduleAutosave } from './persistence/layoutStore';
import { DEFAULT_SHORTCUTS, LONG_PRESS_MS, actionFor, keyOf, nextFitMode, rebind, watermark } from './ChartShortcuts';
import { clipboardState, composeExportSvg, exportPlan } from './ChartExport';
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
}) {
  const [atlas, setAtlas] = useState(false);
  const [quality, setQuality] = useState(null);
  const [layoutId, setLayoutId] = useState('single');
  const [panes, dispatch] = useReducer(panesReducer, undefined, () => createPanes(1, ticker));
  const [layoutNote, setLayoutNote] = useState('');
  const [layoutsOpen, setLayoutsOpen] = useState(false);
  const [shortcuts, setShortcuts] = useState(DEFAULT_SHORTCUTS);
  const [rebindAction, setRebindAction] = useState(null);
  const [fitMode, setFitMode] = useState('fit-visible');
  const [replaying, setReplaying] = useState(false);
  const [exportNote, setExportNote] = useState('');
  const restored = useRef(false);
  const longPressTimer = useRef(null);
  const history = { ticker, open, primary, toolbarActions, forcedScope, onRecordNodes, showAtlas, exposureLine, darkLevels, flowBars, cvdLine };

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
              ? <PriceNodeHistory {...history} onQuality={setQuality} />
              : <PriceNodeHistory ticker={pane.symbol} open={open} primary={false} showAtlas={showAtlas} />)}
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

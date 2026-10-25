import React, { useState } from 'react';
// The INDICATOR BROWSER — the visible, searchable, grouped catalog with
// active-instance settings (the owner's missing-indicator outcome).
// PURE PRESENTATION over the frozen registry/anchor engine: all state and
// data arrive via props; every mutation reports through ONE callback. H1
// mounts this in the Stock toolbar/right workspace and owns the real panes.
//
// Honesty rules baked into the rows: source-gated panes show WHY they are
// unavailable BEFORE any click (no fake Add); Volume is the REAL measured
// volume pane's toggle — it never creates a dead record; exposure-vwap
// carries its typed refusal, not an Add button.
import { STUDY_PRESETS, paneEligibility } from './registry';
import { anchorCoverage } from './anchorStudies';
import './indicators.css';

const GROUPS = [
  { id: 'price', label: 'Price overlays' },
  { id: 'panes', label: 'Panes & flow' },
  { id: 'context', label: 'Context' },
];
const CATALOG = [
  { group: 'price', kind: 'sma', name: 'SMA', keywords: 'simple moving average' },
  { group: 'price', kind: 'ema', name: 'EMA', keywords: 'exponential moving average' },
  { group: 'price', kind: 'bollinger', name: 'Bollinger', keywords: 'bb bands deviation' },
  { group: 'price', kind: 'vwap', name: 'VWAP', keywords: 'volume weighted average price session week month quarter year' },
  { group: 'panes', kind: 'volume', pane: 'volume-pane', name: 'Volume', keywords: 'measured volume bars' },
  { group: 'panes', kind: 'cvd', pane: 'cvd', name: 'CVD', keywords: 'cumulative volume delta estimated' },
  { group: 'panes', kind: 'profile', pane: 'profile', name: 'Volume profile', keywords: 'value area poc visible bars' },
  { group: 'context', kind: 'exposure-vwap', name: 'Exposure VWAP', keywords: 'gex board eligible' },
];
const DEFAULT_SETTINGS = {
  sma: { period: 20 },
  ema: { period: 20 },
  bollinger: { period: 20, multiple: 2 },
  vwap: { source: 'hlc3', bandBasis: 'std', multipliers: [1, 2, 3], bands: false, anchor: 'session' },
};
const ANCHORS = ['session', 'week', 'month', 'quarter', 'year'];
const PRESET_CHIPS = { ema: 'EMA 9', sma: 'SMA 20', bollinger: 'Bollinger 20 · 2σ', vwap: 'VWAP · session' };

const instanceLabel = (inst) => {
  const s = inst.settings || {};
  if (inst.kind === 'sma') return `SMA ${s.period}`;
  if (inst.kind === 'ema') return `EMA ${s.period}`;
  if (inst.kind === 'bollinger') return `BB ${s.period} · ${s.multiple}σ`;
  if (inst.kind === 'vwap') return `VWAP ${s.source || 'hlc3'} · ${s.anchor || 'session'}`;
  return inst.kind;
};

export default function IndicatorsPanel({
  instances = [], frames = [], builtinVwapOn = false,
  paneState = {}, availability = {},
  onCreate = null, onUpdateSettings = null, onRemove = null, onToggleVisible = null, onTogglePane = null,
}) {
  const [query, setQuery] = useState('');
  const [draftMultiplier, setDraftMultiplier] = useState({});
  const q = query.trim().toLowerCase();
  const rows = CATALOG.filter((r) => !q || (r.name + ' ' + r.keywords).toLowerCase().includes(q));
  const active = Array.isArray(instances) ? instances : [];

  const num = (v, min, max, fallback) => {
    const n = Number(v);
    return Number.isFinite(n) && n >= min && n <= max ? Math.round(n) : fallback;
  };

  const update = (inst, patch) => onUpdateSettings && onUpdateSettings(inst.instanceId, { ...inst.settings, ...patch });

  const coverageText = (inst) => {
    const anchor = (inst.settings && inst.settings.anchor) || 'session';
    const cov = anchorCoverage(frames, anchor);
    if (cov.coverage === 'none') return 'no loaded bars';
    const state = cov.coverage === 'partial'
      ? `partial · ${anchor}-to-date within loaded bars (period from ${cov.periodStart})`
      : 'full period loaded';
    const minNote = cov.minBarsState === 'insufficient' ? ' · fewer than 2 measured bars: no value' : '';
    return `${state} · ${cov.groups} ${anchor} group${cov.groups === 1 ? '' : 's'} · ${cov.firstGroupKey} → ${cov.lastGroupKey}${minNote}`;
  };

  const paneRow = (row) => {
    const key = row.pane;
    if (row.kind === 'volume') {
      // The REAL measured volume pane — a toggle, never a fake Add.
      const on = !!paneState[key];
      return (
        <div className="ind-row" data-testid={'catalog-row-' + row.kind} key={row.kind}>
          <span className="ind-name">{row.name}</span>
          <span className="ind-note">measured volume pane</span>
          {onTogglePane && (
            <button type="button" data-testid={'pane-toggle-' + key} aria-pressed={on}
              onClick={() => onTogglePane(key)}>{on ? 'On' : 'Off'}</button>
          )}
        </div>
      );
    }
    const available = availability[row.kind] === true;
    if (!available) {
      return (
        <div className="ind-row ind-unavailable" data-testid={'pane-unavailable-' + row.kind} key={row.kind}>
          <span className="ind-name">{row.name}</span>
          <span className="ind-note">no admitted source — honestly unavailable</span>
        </div>
      );
    }
    const on = !!paneState[key];
    return (
      <div className="ind-row" data-testid={'catalog-row-' + row.kind} key={row.kind}>
        <span className="ind-name">{row.name}</span>
        {onTogglePane && (
          <button type="button" data-testid={'pane-toggle-' + key} aria-pressed={on}
            onClick={() => onTogglePane(key)}>{on ? 'On' : 'Off'}</button>
        )}
      </div>
    );
  };

  const catalogRow = (row) => {
    if (row.group === 'panes') return paneRow(row);
    if (row.kind === 'exposure-vwap') {
      const why = paneEligibility('exposure-vwap', frames);
      return (
        <div className="ind-row ind-unavailable" data-testid={'catalog-row-' + row.kind} key={row.kind}>
          <span className="ind-name">{row.name}</span>
          <span className="ind-note">{why.reason}</span>
        </div>
      );
    }
    const el = paneEligibility(row.kind, frames);
    const chip = PRESET_CHIPS[row.kind];
    return (
      <div className="ind-row" data-testid={'catalog-row-' + row.kind} key={row.kind}>
        <span className="ind-name">{row.name}</span>
        {el.ok ? (
          <span className="ind-actions">
            {chip && onCreate && (
              <button type="button" className="ind-chip" data-testid={'catalog-preset-' + chip}
                title={chip}
                onClick={() => onCreate(STUDY_PRESETS[chip].kind, STUDY_PRESETS[chip].settings)}>{chip}</button>
            )}
            {onCreate && (
              <button type="button" data-testid={'catalog-add-' + row.kind}
                onClick={() => onCreate(row.kind, DEFAULT_SETTINGS[row.kind])}>Add</button>
            )}
          </span>
        ) : (
          <span className="ind-note">{el.reason}</span>
        )}
      </div>
    );
  };

  const settingsEditor = (inst) => {
    const id = inst.instanceId;
    const s = inst.settings || {};
    if (inst.kind === 'sma' || inst.kind === 'ema' || inst.kind === 'bollinger') {
      return (
        <span className="ind-editors">
          <label>Period
            <input type="number" min={inst.kind === 'bollinger' ? 10 : 1} max={500}
              data-testid={'instance-period-' + id} value={s.period}
              onChange={(e) => update(inst, { period: num(e.target.value, inst.kind === 'bollinger' ? 10 : 1, 500, s.period) })} />
          </label>
          {inst.kind === 'bollinger' && (
            <label>σ
              <input type="number" min={0.5} max={5} step={0.5}
                data-testid={'instance-multiple-' + id} value={s.multiple}
                onChange={(e) => {
                  const m = Number(e.target.value);
                  if (Number.isFinite(m) && m >= 0.5 && m <= 5) update(inst, { multiple: m });
                }} />
            </label>
          )}
        </span>
      );
    }
    if (inst.kind === 'vwap') {
      const draft = draftMultiplier[id] || '';
      const mults = Array.isArray(s.multipliers) ? s.multipliers : [];
      const addMultiplier = () => {
        const m = Number(draft);
        if (!Number.isFinite(m) || m < 0.5 || m > 5) return;
        if (mults.length >= 3 || mults.includes(m)) return; // max 3 pairs (C116)
        update(inst, { multipliers: [...mults, m] });
        setDraftMultiplier((d) => ({ ...d, [id]: '' }));
      };
      return (
        <span className="ind-editors">
          <label>Source
            <select data-testid={'instance-source-' + id} value={s.source || 'hlc3'}
              onChange={(e) => update(inst, { source: e.target.value })}>
              <option value="hlc3">HLC3 (bar approximation)</option>
              <option value="close">Close (trade exact)</option>
            </select>
          </label>
          <label>Anchor
            <select data-testid={'instance-anchor-' + id} value={s.anchor || 'session'}
              onChange={(e) => update(inst, { anchor: e.target.value })}>
              {ANCHORS.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </label>
          <label>Basis
            <select data-testid={'instance-basis-' + id} value={s.bandBasis || 'std'}
              onChange={(e) => update(inst, { bandBasis: e.target.value })}>
              <option value="std">σ</option>
              <option value="percent">%</option>
            </select>
          </label>
          <label className="ind-check">
            <input type="checkbox" data-testid={'instance-bands-' + id}
              checked={!!s.bands}
              onChange={(e) => update(inst, { bands: e.target.checked })} />Bands
          </label>
          <span className="ind-mults" data-testid={'instance-multipliers-' + id}>
            {mults.map((m) => (
              <span className="ind-mult" key={String(m)}>
                {m}{onUpdateSettings && (
                  <button type="button" className="ind-mult-x" data-testid={'instance-multiplier-remove-' + id + '-' + m}
                    title={'Remove ' + m} onClick={() => update(inst, { multipliers: mults.filter((x) => x !== m) })}>×</button>
                )}
              </span>
            ))}
            {onUpdateSettings && mults.length < 3 && (
              <span className="ind-mult-add">
                <input type="number" min={0.5} max={5} step={0.5} placeholder="+σ"
                  data-testid={'instance-multiplier-input-' + id} value={draft}
                  onChange={(e) => setDraftMultiplier((d) => ({ ...d, [id]: e.target.value }))} />
                <button type="button" data-testid={'instance-multiplier-add-' + id} onClick={addMultiplier}>+</button>
              </span>
            )}
            <span className="ind-note" data-testid={'instance-multiplier-note-' + id}>up to 3 band pairs</span>
          </span>
          <span className="ind-note" data-testid={'instance-coverage-' + id}>{coverageText(inst)}</span>
        </span>
      );
    }
    return null;
  };

  return (
    <div className="indicators-panel" data-testid="indicators-panel" role="group" aria-label="Indicators">
      <div className="ind-head">
        <strong>Indicators</strong>
        <input type="search" placeholder="Search indicators" data-testid="indicators-search"
          aria-label="Search indicators" value={query} onChange={(e) => setQuery(e.target.value)} />
        {active.length > 0 && <span className="ind-count" data-testid="indicators-active-count">{active.length} active</span>}
      </div>
      {builtinVwapOn && active.some((i) => i.kind === 'vwap') && (
        <div className="ind-note-row" data-testid="builtin-vwap-note">
          The chart's default VWAP overlay is already on — this instance adds an independent line. Turn the overlay off to avoid duplication.
        </div>
      )}
      {GROUPS.filter((g) => rows.some((r) => r.group === g.id)).map((g) => (
        <div className="ind-group" data-testid={'indicators-group-' + g.id} key={g.id}>
          <div className="ind-group-label">{g.label}</div>
          {rows.filter((r) => r.group === g.id).map(catalogRow)}
        </div>
      ))}
      {!!active.length && (
        <div className="ind-active" data-testid="indicators-active">
          <div className="ind-group-label">Active instances</div>
          {active.map((inst) => (
            <div className="ind-instance" data-testid={'indicator-instance-' + inst.instanceId} key={inst.instanceId}>
              <span className="ind-instance-head">
                <span className="ind-name">{instanceLabel(inst)}</span>
                {onToggleVisible && (
                  <button type="button" data-testid={'instance-visible-' + inst.instanceId}
                    aria-pressed={inst.visible !== false}
                    title={inst.visible !== false ? 'Hide' : 'Show'}
                    onClick={() => onToggleVisible(inst.instanceId)}>{inst.visible !== false ? '👁' : '–'}</button>
                )}
                {onRemove && (
                  <button type="button" data-testid={'instance-remove-' + inst.instanceId}
                    onClick={() => onRemove(inst.instanceId)}>Remove</button>
                )}
              </span>
              {settingsEditor(inst)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export { IndicatorsPanel };

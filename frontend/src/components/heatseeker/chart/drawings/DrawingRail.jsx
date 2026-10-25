import React from 'react';
// G10 drawings rail: additive list over the drawing reducer. Selection,
// deletion, lock and hide only — no broker writes. Evaluation/server
// ownership of alerts is untouched by this rail.
// B16: the rail also mounts CREATION (tool picks from the registry), UNDO and
// draft CANCEL — every pinned testid/label above is byte-identical.
// B17/CHART-C091/C129: the rail mounts the VISIBLE preset manager as an
// all-optional section — with no preset props it renders the exact pre-B17
// rail. Presets are caller-owned state (ChartWorkspace wiring is H1's); this
// UI only reports through the callbacks below. Style edits NEVER autosave
// into a preset; a preset's style changes only through the explicit Update
// button, enabled solely on the linked preset while it differs.
import { PRESET_CAP, isDirty } from './presetSchema';
export default function DrawingRail({ drawings = [], selectedId = null,
  onSelect = null, onDelete = null, onToggleLock = null, onToggleHide = null,
  tools = [], draftTool = null, onToolPick = null, onUndo = null, onCancelDraft = null, onStyle = null,
  presets = null, presetScope = null, onPresetCreate = null, onPresetUpdate = null,
  onPresetApply = null, onPresetToggleStar = null, onPresetDelete = null, onPresetSetActive = null }) {
  const [presetName, setPresetName] = React.useState('');
  const selected = (Array.isArray(drawings) ? drawings : []).find((d) => d.id === selectedId) || null;
  const presetList = Array.isArray(presets) ? presets : null;
  const showPresets = presetList !== null;
  const atCap = showPresets && presetList.length >= PRESET_CAP;
  const lockedRefuses = !selected || !!selected.locked;
  const linkedDirtyId = showPresets && selected && !selected.locked
    ? (presetList.find((p) => p && p.id === selected.presetId && isDirty(selected, p)) || {}).id
    : undefined;
  return (
    <div data-testid="drawing-rail" aria-label="Drawings">
      {!!tools.length && (
        <div className="rail-tools" role="group" aria-label="Drawing tools">
          {tools.map(tool => (
            <button key={tool.id} type="button" data-testid={'rail-tool-' + tool.id}
              aria-pressed={draftTool === tool.id}
              onClick={() => onToolPick?.(tool.id)}>
              {tool.id}
            </button>
          ))}
        </div>
      )}
      {(!!drawings.length || draftTool) && onUndo && (
        <button type="button" data-testid="rail-undo" disabled={!drawings.length} onClick={() => onUndo()}>Undo drawing</button>
      )}
      {draftTool && onCancelDraft && (
        <button type="button" data-testid="rail-cancel" onClick={() => onCancelDraft()}>Cancel drawing</button>
      )}
      {selected && onStyle && !selected.locked && (
        <div className="rail-style-row" data-testid="rail-style-row" role="group" aria-label="Selected drawing style">
          <label>Color
            <select data-testid="rail-style-color" aria-label="Drawing color"
              value={selected.style?.color || ""}
              onChange={e => onStyle(selected.id, e.target.value ? { color: e.target.value } : { color: undefined })}>
              <option value="">Default</option>
              <option value="#7fa6c0">Blue</option>
              <option value="#e3c16a">Gold</option>
              <option value="#5ec986">Green</option>
              <option value="#d65656">Red</option>
              <option value="#c4a1ef">Violet</option>
            </select>
          </label>
          <label>Width
            <select data-testid="rail-style-width" aria-label="Drawing width"
              value={String(selected.style?.width || "")}
              onChange={e => onStyle(selected.id, e.target.value ? { width: Number(e.target.value) } : { width: undefined })}>
              <option value="">Default</option>
              <option value="1">1</option>
              <option value="2">2</option>
              <option value="3">3</option>
            </select>
          </label>
          <label><input type="checkbox" data-testid="rail-style-dash" aria-label="Dashed line"
            checked={!!selected.style?.dash}
            onChange={e => onStyle(selected.id, { dash: e.target.checked })} />Dashed</label>
        </div>
      )}
      {showPresets && (
        <div className="rail-presets" data-testid="rail-presets" role="group" aria-label="Drawing presets">
          {presetScope && <div className="rail-presets-scope" data-testid="rail-presets-scope">Presets · {presetScope}</div>}
          {!atCap && onPresetCreate && (
            <div className="rail-preset-create-row">
              <input type="text" data-testid="rail-preset-name" aria-label="New preset name"
                placeholder="Preset name" value={presetName}
                onChange={(e) => setPresetName(e.target.value)} />
              <button type="button" data-testid="rail-preset-create"
                disabled={lockedRefuses || !presetName.trim()}
                onClick={() => { onPresetCreate({ name: presetName.trim(), tool: selected.tool, style: selected.style }); setPresetName(''); }}>
                Save as preset
              </button>
            </div>
          )}
          {atCap && <div className="rail-preset-cap" data-testid="rail-preset-cap" role="status">Preset limit reached (50) — delete one to save another.</div>}
          {presetList.map((p) => (
            <div key={p.id} data-testid="rail-preset" data-starred={!!p.starred} data-active={!!p.active} data-builtin={p.kind === 'built-in'}>
              <span data-testid={'rail-preset-name-' + p.id}>{p.name}{p.active ? ' · active' : ''}{p.kind === 'built-in' ? ' · built-in' : ''}</span>
              {p.id === linkedDirtyId && <span className="rail-preset-dirty" data-testid={'rail-preset-dirty-' + p.id} title="Selected drawing differs from this preset">• modified</span>}
              {onPresetApply && <button type="button" data-testid={'rail-preset-apply-' + p.id}
                disabled={lockedRefuses} onClick={() => onPresetApply(p.id)}>Apply</button>}
              {onPresetToggleStar && p.kind !== 'built-in' && <button type="button" data-testid={'rail-preset-star-' + p.id}
                onClick={() => onPresetToggleStar(p.id)}>{p.starred ? 'Unstar' : 'Star'}</button>}
              {onPresetSetActive && p.kind !== 'built-in' && <button type="button" data-testid={'rail-preset-active-' + p.id}
                onClick={() => onPresetSetActive(p.id)}>{p.active ? 'Active' : 'Set active'}</button>}
              {onPresetUpdate && <button type="button" data-testid={'rail-preset-update-' + p.id}
                disabled={lockedRefuses || p.id !== linkedDirtyId}
                onClick={() => onPresetUpdate(p.id, selected.style)}>Update</button>}
              {onPresetDelete && p.kind !== 'built-in' && <button type="button" data-testid={'rail-preset-delete-' + p.id}
                onClick={() => onPresetDelete(p.id)}>Delete</button>}
            </div>
          ))}
        </div>
      )}
      {(Array.isArray(drawings) ? drawings : []).map((d) => (
        <div key={d.id} data-testid="rail-drawing" data-selected={d.id === selectedId}
          data-locked={!!d.locked} data-visible={d.visible !== false}>
          <span>{d.tool} · {d.id}</span>
          <button type="button" data-testid={'rail-select-' + d.id} onClick={() => onSelect?.(d.id)}>Select</button>
          <button type="button" data-testid={'rail-delete-' + d.id} onClick={() => onDelete?.(d.id)}>Delete</button>
          <button type="button" data-testid={'rail-lock-' + d.id} onClick={() => onToggleLock?.(d.id)}>
            {d.locked ? 'Unlock' : 'Lock'}
          </button>
          <button type="button" data-testid={'rail-hide-' + d.id} onClick={() => onToggleHide?.(d.id)}>
            {d.visible === false ? 'Show' : 'Hide'}
          </button>
        </div>
      ))}
    </div>
  );
}

import React from 'react';
// G10 drawings rail: additive list over the drawing reducer. Selection,
// deletion, lock and hide only — no broker writes. Evaluation/server
// ownership of alerts is untouched by this rail.
// B16: the rail also mounts CREATION (tool picks from the registry), UNDO and
// draft CANCEL — every pinned testid/label above is byte-identical.
export default function DrawingRail({ drawings = [], selectedId = null,
  onSelect = null, onDelete = null, onToggleLock = null, onToggleHide = null,
  tools = [], draftTool = null, onToolPick = null, onUndo = null, onCancelDraft = null, onStyle = null }) {
  const selected = (Array.isArray(drawings) ? drawings : []).find((d) => d.id === selectedId) || null;
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

import React from 'react';
// G10 drawings rail: additive list over the drawing reducer. Selection,
// deletion, lock and hide only — no broker writes. Evaluation/server
// ownership of alerts is untouched by this rail.
// B16: the rail also mounts CREATION (tool picks from the registry), UNDO and
// draft CANCEL — every pinned testid/label above is byte-identical.
export default function DrawingRail({ drawings = [], selectedId = null,
  onSelect = null, onDelete = null, onToggleLock = null, onToggleHide = null,
  tools = [], draftTool = null, onToolPick = null, onUndo = null, onCancelDraft = null }) {
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

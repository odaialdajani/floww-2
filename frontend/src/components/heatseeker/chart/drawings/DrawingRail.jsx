import React from 'react';
// G10 drawings rail: additive list over the drawing reducer. Selection,
// deletion, lock and hide only — no canvas editing, no broker writes.
// Evaluation/server ownership of alerts is untouched by this rail.
export default function DrawingRail({ drawings = [], selectedId = null,
  onSelect = null, onDelete = null, onToggleLock = null, onToggleHide = null }) {
  return (
    <div data-testid="drawing-rail" aria-label="Drawings">
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

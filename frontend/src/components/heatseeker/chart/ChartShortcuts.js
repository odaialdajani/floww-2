// B27 shortcuts/usability: never inside typing fields, focus/escape, touch replay
// above chips, two auto-fit modes, watermarks for source/proxy/replay.
// Keyboard map is rebindable and mounted by ChartWorkspace — this module owns
// the rules, the workspace owns the wiring.
export function shouldHandleShortcut(event) {
  const tag = event?.target?.tagName;
  return tag !== 'INPUT' && tag !== 'TEXTAREA';
}

export function isTypingField(el) {
  const tag = el?.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || el?.isContentEditable === true;
}

export const DEFAULT_SHORTCUTS = {
  escape: 'escape',
  atlas: 'a',
  layouts: 'l',
  cycleLayout: 'c',
  fitMode: 'f',
  replay: 'r',
};

export const REBINDABLE_ACTIONS = Object.keys(DEFAULT_SHORTCUTS);
export const LONG_PRESS_MS = 500;

export function keyOf(event) {
  return String(event?.key ?? '').toLowerCase();
}

// The single dispatch rule: typing fields never fire chart shortcuts, and
// modifier combos (Alt/Ctrl/Meta) never fire the rebindable single-key map —
// those belong to focused handlers (CHART-C090's Alt+L/Alt+S risk armer).
export function actionFor(map, event) {
  if (!shouldHandleShortcut(event)) return null;
  if (event?.altKey || event?.ctrlKey || event?.metaKey) return null;
  const key = keyOf(event);
  for (const action of REBINDABLE_ACTIONS) {
    if (map[action] === key) return action;
  }
  return null;
}

// Rebinding: only known actions, single printable keys, no reserved escape
// binding for non-escape actions, no key that would make the map ambiguous
// (two actions on one key) — refusal is typed.
export function rebind(map, action, key) {
  if (!REBINDABLE_ACTIONS.includes(action)) throw new Error('unknown-action');
  const normalized = String(key ?? '').toLowerCase();
  if (action !== 'escape' && normalized === 'escape') throw new Error('reserved-key');
  if (!normalized || normalized === ' ' || normalized.length > 1) throw new Error('bad-key');
  if (Object.entries(map).some(([a, k]) => a !== action && k === normalized)) throw new Error('ambiguous-key');
  return { ...map, [action]: normalized };
}

export const FIT_MODES = ['fit-visible', 'fit-all'];

export function nextFitMode(mode) {
  const index = FIT_MODES.indexOf(mode);
  return FIT_MODES[(index + 1) % FIT_MODES.length] ?? FIT_MODES[0];
}

export function watermark({ source, proxy, replay }) {
  const parts = [];
  if (source) parts.push(`source:${source}`);
  if (proxy) parts.push(`proxy:${proxy}`);
  if (replay) parts.push('replay');
  return parts.join(' ');
}

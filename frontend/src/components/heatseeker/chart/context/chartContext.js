// B24 server-resolved focused-chart AI context — client display mirror of
// backend/services/chart_context.py. The SERVER stays the resolver of facts;
// this mirror only represents the bind/resolve contract on the client so the
// focused chart can show its context state honestly and the ask gate can
// refuse stale races. Client numbers are never evidence; no trade
// recommendations.

// Create a resolvable descriptor; refuses incomplete binding.
export function bindContext({ focus, query, scope, cursor, generation }) {
  if (!focus || !query || !scope || cursor == null || generation == null) {
    return { status: 'refused', reason: 'incomplete binding' };
  }
  return { status: 'bound', focus, query, scope, cursor, generation };
}

// Admit only the exact generation with a matching scope on a live pane;
// stale generations, scope changes and removed panes all refuse — a race can
// never re-admit stale context.
export function resolveContext(descriptor, current) {
  if (!descriptor || typeof descriptor !== 'object' || descriptor.status !== 'bound') {
    return { status: 'refused', reason: 'unbound' };
  }
  if (descriptor.generation !== (current && current.generation)) {
    return { status: 'refused', reason: 'stale generation' };
  }
  if (descriptor.scope !== (current && current.scope)) {
    return { status: 'refused', reason: 'scope mismatch' };
  }
  if (current && current.pane_removed) {
    return { status: 'refused', reason: 'pane removed' };
  }
  return { status: 'admitted', focus: descriptor.focus };
}

// B05 generation-safe shared chart data hook.
// Per-pane sessions: every chart pane owns its generation counter and
// inflight registry, so one pane's refresh can never invalidate another
// pane's in-flight query (the old module-global design did exactly that).
// The hook aborts stale symbol/interval/session/scope generations, shares
// one in-flight query per pane key (dedupe), surfaces explicit
// stale/cache/budget/outage badges, and lets reconnect backfill replace
// corrections without merging into a live generation silently.
import { useCallback, useEffect, useRef, useState } from 'react';

// Pure helpers — semantics unchanged from the accepted contract.
export function dedupeKey({ symbol, interval, session, scope }) {
  return [symbol, interval, session, scope].join('|');
}
export function isStale(resultGen, activeGen) { return resultGen !== activeGen; }
export function badgeFor({ stale, cached, budget, outage }) {
  if (outage) return 'outage';
  if (budget) return 'budget-exhausted';
  if (stale) return 'stale';
  if (cached) return 'cached';
  return 'live';
}

// A pane-scoped session: private generation + private inflight map.
export function createChartSession() {
  let generation = 0;
  const inflight = new Map();
  return {
    nextGeneration() { generation += 1; return generation; },
    currentGeneration() { return generation; },
    registerQuery(key, gen) { inflight.set(key, gen); return gen; },
    shouldApply(key, gen) { return inflight.get(key) === gen && gen === generation; },
    clearQuery(key) { inflight.delete(key); },
  };
}

// Module-default session retained for the legacy single-consumer helpers.
const defaultSession = createChartSession();
export const nextGeneration = () => defaultSession.nextGeneration();
export const currentGeneration = () => defaultSession.currentGeneration();
export const registerQuery = (key, gen) => defaultSession.registerQuery(key, gen);
export const shouldApply = (key, gen) => defaultSession.shouldApply(key, gen);

// Correction/backfill replacement binds to the ACTIVE generation of the
// supplied session, so a late correction for a dead generation never lands.
export function backfillReplace(current, correction, activeGeneration = defaultSession.currentGeneration()) {
  if (!correction || correction.generation !== activeGeneration) return current;
  return correction.data;
}

// Mounted per-pane request lifecycle. `fetcher({ symbol, interval, session,
// scope, signal })` resolves to `{ data, stale?, cached?, budgetExhausted?,
// outage?, error? }` or rejects ({ budgetExhausted?, outage? } on the error).
export function useChartData({ symbol, interval = '5m', session = 'rth', scope = '', fetcher, enabled = true }) {
  const sessionRef = useRef(null);
  if (!sessionRef.current) sessionRef.current = createChartSession();
  const paneSession = sessionRef.current;
  const [data, setData] = useState(null);
  const [status, setStatus] = useState('idle'); // idle | loading | ready | error
  const [meta, setMeta] = useState({ stale: false, cached: false, budget: false, outage: false });
  const inflightRef = useRef(new Map()); // key -> { gen, controller, shared }
  const key = dedupeKey({ symbol, interval, session, scope });

  const load = useCallback(async () => {
    if (!fetcher || !enabled) return undefined;
    // Abort stale identities: any in-flight query for a DIFFERENT pane key
    // belongs to a superseded symbol/interval/session/scope generation.
    for (const [k, rec] of inflightRef.current) {
      if (k !== key) { rec.controller.abort(); inflightRef.current.delete(k); }
    }
    // Dedupe: a second request for the same pane key shares the in-flight query.
    const existing = inflightRef.current.get(key);
    if (existing) { existing.shared += 1; return undefined; }
    const gen = paneSession.nextGeneration();
    const controller = typeof AbortController === 'function' ? new AbortController() : { abort() {}, signal: { aborted: false } };
    paneSession.registerQuery(key, gen);
    inflightRef.current.set(key, { gen, controller, shared: 1 });
    setStatus('loading');
    try {
      const outcome = (await fetcher({ symbol, interval, session, scope, signal: controller.signal })) || {};
      if (controller.signal.aborted || !paneSession.shouldApply(key, gen)) return undefined;
      setMeta({ stale: !!outcome.stale, cached: !!outcome.cached, budget: !!outcome.budgetExhausted, outage: !!outcome.outage });
      setData(typeof outcome.data === 'undefined' ? null : outcome.data);
      setStatus(outcome.error ? 'error' : 'ready');
    } catch (error) {
      if (controller.signal.aborted || !paneSession.shouldApply(key, gen)) return undefined;
      const e = error || {};
      setMeta({ stale: false, cached: false, budget: !!e.budgetExhausted, outage: !!e.outage });
      setStatus('error');
    } finally {
      const rec = inflightRef.current.get(key);
      if (rec && rec.gen === gen) inflightRef.current.delete(key);
    }
    return undefined;
  }, [fetcher, enabled, key, symbol, interval, session, scope, paneSession]);

  useEffect(() => { load(); }, [load]);
  // Unmount: abort every in-flight query this pane owns.
  useEffect(() => () => {
    for (const rec of inflightRef.current.values()) rec.controller.abort();
    inflightRef.current.clear();
  }, []);

  return { data, status, badge: badgeFor(meta), meta, refresh: load, session: paneSession };
}

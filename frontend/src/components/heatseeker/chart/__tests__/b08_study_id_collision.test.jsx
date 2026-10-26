// B08 study-instance ID collisions after a REAL module reset (C045 reload
// safety), 2026-10-25. The counterexample from study-id-repro.md: a browser
// reload starts the registry's module counter at 1 again while persisted
// instances keep their ids — a fresh module re-mints an id a restored row
// already owns, the store persists both, and the caller's map-update /
// filter-remove BY ID then hits BOTH rows. These regressions use REAL module
// resets (jest.resetModules + require, fresh module lifetimes over the SAME
// jsdom localStorage — exactly a reload's semantics), never a counter bump
// inside one module. No React render here on purpose: resetModules
// re-requires React itself and two React copies in one jsdom break hooks.
//
// Deliberately NOT asserted: exact minted-id bytes for NEW instances (they
// carry a module-lifetime token by design). Asserted instead: distinctness,
// stability across reloads, legacy-id preservation, deterministic repair.
const requireModules = () => {
  jest.resetModules();
  return {
    registry: require('../indicators/registry'),
    store: require('../persistence/studyStore'),
  };
};

test('fresh-module reload: a new instance never re-mints a restored id; caller update/remove hit exactly one row (C045)', () => {
  window.localStorage.clear();
  let { registry, store } = requireModules();
  const original = registry.createStudyInstance('ema', { period: 9 }, 'SPY');
  store.saveStudyInstances('SPY', [original]);

  // REAL reload: fresh module lifetimes, storage retained.
  ({ registry, store } = requireModules());
  const restored = store.loadStudyInstances('SPY');
  expect(restored).toHaveLength(1);
  expect(restored[0].instanceId).toBe(original.instanceId); // legacy id preserved verbatim
  expect(restored[0].settings.period).toBe(9);

  const added = registry.createStudyInstance('ema', { period: 20 }, 'SPY');
  expect(added.instanceId).not.toBe(restored[0].instanceId); // RED today: both mint 'ema-1'

  const combined = [...restored, added];
  store.saveStudyInstances('SPY', combined);

  // Reopen in a third module lifetime: ids stable and set-wide unique.
  ({ registry, store } = requireModules());
  const reopened = store.loadStudyInstances('SPY');
  expect(reopened.map(s => s.instanceId)).toEqual(combined.map(s => s.instanceId));
  expect(new Set(reopened.map(s => s.instanceId)).size).toBe(2);

  // The caller's EXACT update expression by id: only the new row changes.
  const updated = reopened.map(s => (s.instanceId === added.instanceId ? { ...s, settings: { period: 30 } } : s));
  expect(updated.find(s => s.instanceId === original.instanceId).settings.period).toBe(9);
  expect(updated.find(s => s.instanceId === added.instanceId).settings.period).toBe(30);

  // The caller's EXACT remove expression by id: the original survives.
  const remaining = reopened.filter(s => s.instanceId !== added.instanceId);
  expect(remaining).toHaveLength(1);
  expect(remaining[0].instanceId).toBe(original.instanceId);
  expect(remaining[0].settings.period).toBe(9);
});

test('several studies added after a reload stay mutually unique and independently editable', () => {
  window.localStorage.clear();
  let { registry, store } = requireModules();
  store.saveStudyInstances('SPY', [registry.createStudyInstance('ema', { period: 9 }, 'SPY')]);

  ({ registry, store } = requireModules());
  const restored = store.loadStudyInstances('SPY');
  const added = [
    registry.createStudyInstance('ema', { period: 20 }, 'SPY'),
    registry.createStudyInstance('sma', { period: 5 }, 'SPY'),
    registry.createStudyInstance('bollinger', { period: 10, multiple: 2 }, 'SPY'),
    registry.createStudyInstance('volume', {}, 'SPY'),
  ];
  const all = [...restored, ...added];
  expect(all).toHaveLength(5);
  expect(new Set(all.map(s => s.instanceId)).size).toBe(all.length); // RED today: restored ema-1 == new ema-1
  store.saveStudyInstances('SPY', all);

  ({ registry, store } = requireModules());
  const reopened = store.loadStudyInstances('SPY');
  expect(reopened).toHaveLength(5);
  expect(reopened.map(s => s.instanceId)).toEqual(all.map(s => s.instanceId)); // stable, none renumbered

  // Independent edit of the new EMA leaves every other row byte-identical.
  const target = added[0].instanceId;
  const afterEdit = reopened.map(s => (s.instanceId === target ? { ...s, settings: { period: 30 } } : s));
  expect(afterEdit.filter(s => s.instanceId !== target)).toEqual(reopened.filter(s => s.instanceId !== target));
  expect(afterEdit.find(s => s.instanceId === target).settings.period).toBe(30);
  expect(afterEdit.find(s => s.kind === 'ema' && s.settings.period === 9)).toBeTruthy();

  // Independent removal of the volume instance leaves the other four.
  const volumeId = added[3].instanceId;
  const afterRemove = reopened.filter(s => s.instanceId !== volumeId);
  expect(afterRemove).toHaveLength(4);
  expect(afterRemove.map(s => s.instanceId)).toEqual(reopened.filter(s => s.instanceId !== volumeId).map(s => s.instanceId));
});

test('legacy duplicate persisted ids: deterministic repair, first id verbatim, later rows preserved not overwritten', () => {
  window.localStorage.clear();
  const row = (period, id) => ({
    instanceId: id, kind: 'ema', settings: { period }, source: 'close',
    visible: true, order: period, paneKey: 'SPY', created: 1700000000000 + period,
  });
  // A legacy/corrupt persisted set: three valid rows sharing one id.
  window.localStorage.setItem('floww.chart.studies.SPY', JSON.stringify({
    schema_version: 1,
    instances: [row(9, 'ema-1'), row(20, 'ema-1'), row(50, 'ema-1')],
  }));
  const { store } = requireModules();
  const repaired = store.loadStudyInstances('SPY');
  expect(repaired).toHaveLength(3); // no study dropped, none coalesced
  expect(repaired[0].instanceId).toBe('ema-1'); // first-in-stored-order keeps the legacy id
  expect(repaired[0].settings.period).toBe(9);
  expect(repaired[1].instanceId).toBe('ema-1-dup2'); // deterministic re-mint
  expect(repaired[1].settings.period).toBe(20); // the differently configured study is NOT overwritten
  expect(repaired[2].instanceId).toBe('ema-1-dup3');
  expect(repaired[2].settings.period).toBe(50);
  // provenance rides through untouched on re-minted rows
  expect(repaired[1].order).toBe(20);
  expect(repaired[1].created).toBe(1700000000020);
  expect(repaired[1].paneKey).toBe('SPY');

  // Save persists the repaired set; a fresh module reload is stable.
  store.saveStudyInstances('SPY', repaired);
  const { store: reopenedStore } = requireModules();
  const reopened = reopenedStore.loadStudyInstances('SPY');
  expect(reopened.map(s => s.instanceId)).toEqual(['ema-1', 'ema-1-dup2', 'ema-1-dup3']);
  expect(new Set(reopened.map(s => s.instanceId)).size).toBe(3);

  // Crafted collision: a real 'ema-1-dup2' row already exists — the repair
  // must skip that id, not steal it.
  window.localStorage.setItem('floww.chart.studies.QQQ', JSON.stringify({
    schema_version: 1,
    instances: [row(9, 'ema-1'), row(20, 'ema-1'), row(50, 'ema-1-dup2')],
  }));
  const { store: qqStore } = requireModules();
  const qq = qqStore.loadStudyInstances('QQQ');
  expect(qq.map(s => s.instanceId)).toEqual(['ema-1', 'ema-1-dup3', 'ema-1-dup2']);
  expect(qq.map(s => s.settings.period)).toEqual([9, 20, 50]);
});

test('the store never persists duplicate ids even when handed a duplicated list', () => {
  window.localStorage.clear();
  const { store } = requireModules();
  const row = (period, id) => ({
    instanceId: id, kind: 'ema', settings: { period }, source: 'close',
    visible: true, order: period, paneKey: 'SPY', created: 1700000000000 + period,
  });
  store.saveStudyInstances('SPY', [row(9, 'ema-1'), row(21, 'ema-1')]);
  const loaded = store.loadStudyInstances('SPY');
  expect(loaded).toHaveLength(2); // both studies survive
  expect(new Set(loaded.map(s => s.instanceId)).size).toBe(2); // RED today: 'ema-1' twice
  expect(loaded[0].instanceId).toBe('ema-1');
  expect(loaded[0].settings.period).toBe(9);
  expect(loaded[1].settings.period).toBe(21);
  // existing refusal contract bytes stay intact for the caller's UX
  expect(() => store.saveStudyInstances('SPY', [{ instanceId: 'bad', kind: 'ema', settings: { period: 0 } }])).toThrow('invalid study instance');
});

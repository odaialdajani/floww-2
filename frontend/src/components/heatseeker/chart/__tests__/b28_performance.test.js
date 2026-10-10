import { makeScenario, cullViewport, BUDGETS } from '../performanceScenario';
test('perf scenario measured + culling + budgets', () => {
  const s = makeScenario({ bars: 10000, nodesPerBar: 20, panes: 1, dpr: 1 });
  expect(s.totalPrimitives).toBe(200000);
  const all = Array.from({ length: 10000 }, (_, i) => i);
  const t0 = performance.now();
  const vis = cullViewport(all, { start: 9900, count: 100 });
  const dt = performance.now() - t0;
  expect(vis).toHaveLength(100);
  expect(dt).toBeLessThan(BUDGETS.frameMs);
  expect(BUDGETS.mountMs).toBe(5000);
});

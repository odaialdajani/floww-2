// B28 perf scenario: 10k bars x20 nodes, panes, DPR, culling, budgets, unmounts.
export function makeScenario({ bars = 10000, nodesPerBar = 20, panes = 1, dpr = 1 } = {}) {
  return { bars, nodesPerBar, panes, dpr, totalPrimitives: bars * nodesPerBar * panes * dpr };
}
export function cullViewport(all, { start, count }) {
  return all.slice(start, start + count);
}
export const BUDGETS = { mountMs: 5000, frameMs: 50, heapMB: 500 };

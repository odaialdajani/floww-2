// B07 exposure settings: independent scope/node selection, mismatch disclosure.
export function resolveExposureSettings({ orbScope, orbNodes, vwapScope, vwapNodes }) {
  const mismatch = orbScope !== vwapScope || orbNodes !== vwapNodes;
  return { orbScope, orbNodes, vwapScope, vwapNodes, mismatch };
}

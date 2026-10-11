// G1-finish: derive the chart's forced scope from live heatmap data.
// Live data carrying the server's exact scope_echo wins; replay snapshots,
// missing echoes, and non-string echoes yield null (chart keeps its own
// latest-scope default and manual picker). Never reconstruct or guess.
export function chartScopeFor(visibleData, isReplay) {
  if (isReplay) return null;
  const echo = visibleData?.scope_echo;
  return typeof echo === 'string' && echo ? echo : null;
}
